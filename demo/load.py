"""Ingest load generator: every seeded source sends events of every demo schema, as fast as it can.

One process, one thread, one asyncio loop. Webhook sources keep `--concurrency` requests in flight each; WebSocket
sources open `--ws-connections` connections each and pipeline up to `--ws-window` frames per connection (the server
answers frames in order, SPEC §6); protobuf sources keep `--concurrency` gRPC calls in flight on one HTTP/2 channel
each (ADR-0097). Prints a status histogram and round-trip percentiles per source.
"""

import argparse
import asyncio
import itertools
import json
import os
import random
import statistics
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import grpc
import httpx
import websockets
from google.protobuf import struct_pb2
from websockets.asyncio.client import ClientConnection

# Generated from contract/proto by `mise run contract`; on the host, run with PYTHONPATH=backend/src.
from pagercutie.v1 import ingest_pb2

type Payload = dict[str, Any]


def level(critical: float = 0.01, error: float = 0.05, warning: float = 0.15) -> str:
    roll = random.random()
    if roll < critical:
        return "CRITICAL"
    if roll < critical + error:
        return "ERROR"
    if roll < critical + error + warning:
        return "WARNING"
    return "INFO"


def http_request() -> Payload:
    status = random.choices([200, 201, 404, 500, 503], weights=[70, 10, 10, 6, 4])[0]
    return {
        "service": random.choice(["checkout-api", "checkout-web", "cart-api"]),
        "method": random.choice(["GET", "POST", "PUT"]),
        "path": random.choice(["/cart", "/checkout", "/pay", "/orders/{id}"]),
        "status": status,
        "latency_ms": round(random.lognormvariate(5, 1), 1),
        "level": "ERROR" if status >= 500 else level(error=0),
    }


def job_run() -> Payload:
    failed = random.random() < 0.15
    payload: Payload = {
        "job": random.choice(["invoice-export", "settlement-sync", "dunning-mailer"]),
        "run_id": str(uuid.uuid4()),
        "outcome": "failed" if failed else "succeeded",
        "duration_s": round(random.uniform(0.5, 120), 2),
        "attempts": random.randint(1, 4) if failed else 1,
        "level": "ERROR" if failed else "INFO",
    }
    if failed:
        payload["error"] = {"code": random.choice(["E_TIMEOUT", "E_UPSTREAM", "E_LOCKED"]), "message": "demo failure"}
    return payload


def host_metric() -> Payload:
    metric = random.choice(["disk_used_pct", "cpu_pct", "mem_used_pct"])
    value = round(random.uniform(20, 99), 1)
    return {
        "host": f"edge-{random.randint(1, 12):02d}",
        "metric": metric,
        "value": value,
        "unit": "percent",
        "level": "CRITICAL" if value > 97 else "WARNING" if value > 90 else "INFO",
    }


def payment_event() -> Payload:
    state = random.choices(["authorized", "captured", "declined", "refunded"], weights=[40, 40, 15, 5])[0]
    return {
        "payment_id": f"pay_{uuid.uuid4().hex[:12]}",
        "amount": round(random.lognormvariate(7, 1.5), 2),
        "currency": random.choice(["EUR", "USD", "CZK"]),
        "state": state,
        "tags": random.sample(["web", "mobile", "test", "recurring"], k=random.randint(0, 2)),
        "level": "WARNING" if state == "declined" else "INFO",
    }


GENERATORS: tuple[Callable[[], Payload], ...] = (http_request, job_run, host_metric, payment_event)


@dataclass
class Stats:
    """Outcomes of one source; `statuses` keys are HTTP statuses, gRPC status names, or `closed:<code>` /
    `error:<type>`."""

    slug: str
    type: str
    statuses: Counter[str] = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)

    def record(self, status: str, started: float) -> None:
        """An answered event, with its round trip since `started` (a `time.perf_counter()` value)."""
        self.statuses[status] += 1
        self.latencies_ms.append((time.perf_counter() - started) * 1000)

    def count(self, status: str) -> None:
        """A connection-level outcome (denied handshake, closed connection), which has no round trip."""
        self.statuses[status] += 1

    @property
    def total(self) -> int:
        return self.statuses.total()


def payload() -> Payload:
    """The next event: generators are cycled per call so every source sends every schema."""
    return next(_cycle)()


def body() -> bytes:
    return json.dumps(payload()).encode()


def grpc_event() -> ingest_pb2.Event:
    struct = struct_pb2.Struct()
    struct.update(payload())
    return ingest_pb2.Event(payload=struct)


_cycle = itertools.cycle(GENERATORS)


async def webhook_worker(client: httpx.AsyncClient, url: str, token: str, stats: Stats, deadline: float) -> None:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    while time.monotonic() < deadline:
        started = time.perf_counter()
        try:
            response = await client.post(url, content=body(), headers=headers)
        except httpx.HTTPError as error:
            stats.record(f"error:{type(error).__name__}", started)
            await asyncio.sleep(0.5)
            continue
        stats.record(str(response.status_code), started)
        if response.status_code == 503:
            # The replica's source catalog is not loaded yet (ADR-0062); back off instead of spinning.
            await asyncio.sleep(0.1)


type Send = grpc.aio.UnaryUnaryMultiCallable[ingest_pb2.Event, ingest_pb2.Accepted]


async def grpc_worker(send: Send, slug: str, token: str, stats: Stats, deadline: float) -> None:
    metadata = (("authorization", f"Bearer {token}"), ("source-slug", slug))
    while time.monotonic() < deadline:
        started = time.perf_counter()
        try:
            await send(grpc_event(), metadata=metadata, timeout=30)
        except grpc.aio.AioRpcError as error:
            stats.record(error.code().name, started)
            if error.code() == grpc.StatusCode.UNAVAILABLE:
                # Catalog not loaded yet, or no connection; back off instead of spinning.
                await asyncio.sleep(0.1)
            continue
        stats.record("OK", started)


def frame_status(reply: str | bytes) -> str:
    """`{"event_id", "matches"}` is the 202 body; errors arrive as `{"status", "detail"}` (SPEC §6)."""
    data = json.loads(reply)
    return "202" if "event_id" in data else str(data.get("status", "unknown"))


async def websocket_connection(url: str, token: str, window: int, stats: Stats, deadline: float) -> None:
    while time.monotonic() < deadline:
        try:
            async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {token}"}) as ws:
                await pipeline(ws, window, stats, deadline)
        except websockets.InvalidStatus as error:
            stats.count(str(error.response.status_code))
            await asyncio.sleep(0.5)
        except websockets.ConnectionClosed as error:
            code = error.rcvd.code if error.rcvd else "none"
            stats.count(f"closed:{code}")
            await asyncio.sleep(0.5)
        except OSError as error:
            stats.count(f"error:{type(error).__name__}")
            await asyncio.sleep(0.5)


async def pipeline(ws: ClientConnection, window: int, stats: Stats, deadline: float) -> None:
    """Keeps up to `window` frames unanswered; replies come back in send order."""
    slots = asyncio.Semaphore(window)
    sent: asyncio.Queue[float] = asyncio.Queue()

    async def send() -> None:
        while time.monotonic() < deadline:
            await slots.acquire()
            await sent.put(time.perf_counter())
            await ws.send(body().decode())

    async def receive() -> None:
        while time.monotonic() < deadline or not sent.empty():
            reply = await ws.recv()
            stats.record(frame_status(reply), sent.get_nowait())
            slots.release()

    sender = asyncio.create_task(send())
    try:
        await receive()
    finally:
        sender.cancel()


def ws_url(base_url: str, ingest_url: str) -> str:
    return base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + ingest_url


def percentile(values: list[float], q: int) -> float:
    return statistics.quantiles(values, n=100)[q - 1] if len(values) > 1 else (values[0] if values else 0.0)


def report(all_stats: list[Stats], elapsed: float) -> None:
    print(f"\n{'source':<18}{'type':<11}{'events':>8}{'ev/s':>9}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}  statuses")
    for stats in all_stats:
        statuses = ", ".join(f"{status}={count}" for status, count in stats.statuses.most_common())
        lat = stats.latencies_ms
        print(
            f"{stats.slug:<18}{stats.type:<11}{stats.total:>8}{stats.total / elapsed:>9.1f}"
            f"{percentile(lat, 50):>9.1f}{percentile(lat, 95):>9.1f}{percentile(lat, 99):>9.1f}  {statuses}"
        )
    total = sum(stats.total for stats in all_stats)
    print(f"{'all':<29}{total:>8}{total / elapsed:>9.1f}")


async def progress(all_stats: list[Stats], started: float, deadline: float) -> None:
    previous, last = 0, started
    while (now := time.monotonic()) < deadline:
        await asyncio.sleep(min(5, deadline - now))
        total, now = sum(stats.total for stats in all_stats), time.monotonic()
        print(f"{now - started:6.0f}s  {total:>8} events  {(total - previous) / (now - last):8.1f} ev/s", flush=True)
        previous, last = total, now


async def run(args: argparse.Namespace) -> None:
    sources: list[dict[str, str]] = json.loads(args.state.read_text())["sources"]
    started = time.monotonic()
    deadline = started + args.duration
    all_stats: list[Stats] = []
    tasks = []
    limits = httpx.Limits(max_connections=args.concurrency * len(sources), max_keepalive_connections=None)
    channels: list[grpc.aio.Channel] = []
    async with httpx.AsyncClient(limits=limits, timeout=30) as client:
        for source in sources:
            stats = Stats(source["slug"], source["type"])
            all_stats.append(stats)
            match source["type"]:
                case "webhook":
                    url = args.base_url + source["ingest_url"]
                    tasks += [
                        webhook_worker(client, url, source["token"], stats, deadline) for _ in range(args.concurrency)
                    ]
                case "websocket":
                    url = ws_url(args.base_url, source["ingest_url"])
                    tasks += [
                        websocket_connection(url, source["token"], args.ws_window, stats, deadline)
                        for _ in range(args.ws_connections)
                    ]
                case "protobuf":
                    # The source's ingest_url is the gRPC method path; one channel per source (ADR-0097).
                    channel = grpc.aio.insecure_channel(args.grpc_target)
                    channels.append(channel)
                    send: Send = channel.unary_unary(
                        source["ingest_url"],
                        request_serializer=ingest_pb2.Event.SerializeToString,
                        response_deserializer=ingest_pb2.Accepted.FromString,
                    )
                    tasks += [
                        grpc_worker(send, source["slug"], source["token"], stats, deadline)
                        for _ in range(args.concurrency)
                    ]
                case other:
                    print(f"skipping {source['slug']}: no load generator for source type {other}")
        print(
            f"{len(sources)} sources, {len(tasks)} workers on one event loop,"
            f" {args.duration:.0f}s against {args.base_url} (gRPC {args.grpc_target})"
        )
        try:
            await asyncio.gather(progress(all_stats, started, deadline), *tasks)
        finally:
            for channel in channels:
                await channel.close()
    report(all_stats, time.monotonic() - started)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("DEMO_BASE_URL", "http://localhost:5173/api"))
    parser.add_argument(
        "--grpc-target",
        default=os.environ.get("DEMO_GRPC_TARGET", "localhost:5173"),
        help="host:port of the gRPC ingest service",
    )
    parser.add_argument("--state", type=Path, default=Path(os.environ.get("DEMO_STATE", "demo-state.json")))
    parser.add_argument("--duration", type=float, default=30, help="seconds")
    parser.add_argument(
        "--concurrency", type=int, default=32, help="requests in flight per webhook source, calls per protobuf source"
    )
    parser.add_argument("--ws-connections", type=int, default=4, help="connections per WebSocket source")
    parser.add_argument("--ws-window", type=int, default=8, help="unanswered frames per WebSocket connection")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
