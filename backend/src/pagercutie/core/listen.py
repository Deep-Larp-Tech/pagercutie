"""Reacting to Postgres `NOTIFY` signals between replicas, over one connection per replica (SPEC §5.3, ADR-0063)."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping

import asyncpg
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from pagercutie.core.broadcast import Broadcast
from pagercutie.core.workers import Worker

log = structlog.get_logger("listen")

MIN_BACKOFF_S = 0.5
MAX_BACKOFF_S = 30.0
HEARTBEAT_S = 10.0
HEARTBEAT_TIMEOUT_S = 5.0

type OnChange = Callable[[], Awaitable[None]]
type OnLost = Callable[[], None]
type Handler = OnChange | Broadcast


class ConnectionLost(Exception):
    """Postgres closed the listening connection."""


async def _set_when(source: asyncio.Event, target: asyncio.Event) -> None:
    await source.wait()
    target.set()


async def _listen_once(
    engine: AsyncEngine,
    handlers: Mapping[str, Handler],
    wake: asyncio.Event,
    stopping: asyncio.Event,
    on_ready: Callable[[], None],
) -> None:
    """Serves one connection until `stopping` is set; raises when the connection is lost or a handler fails."""
    reloaders = {channel: h for channel, h in handlers.items() if not isinstance(h, Broadcast)}
    broadcasts = [h for h in handlers.values() if isinstance(h, Broadcast)]
    changed: set[str] = set(reloaders)
    lost = False

    def on_notification(_connection: object, _pid: int, channel: str, payload: str) -> None:
        handler = handlers[channel]
        if isinstance(handler, Broadcast):
            handler.publish(payload)
        else:
            changed.add(channel)
            wake.set()

    def on_termination(_connection: object) -> None:
        nonlocal lost
        lost = True
        wake.set()

    async with engine.connect() as connection:
        try:
            driver = (await connection.get_raw_connection()).driver_connection
            if not isinstance(driver, asyncpg.Connection):
                raise TypeError(f"LISTEN needs an asyncpg connection, the engine gave {type(driver).__name__}")
            driver.add_termination_listener(on_termination)
            for channel in handlers:
                await driver.add_listener(channel, on_notification)
            for broadcast in broadcasts:
                broadcast.open()
            log.info("listen.connected", message="Listening for notifications", channels=sorted(handlers))
            while not stopping.is_set():
                while changed:
                    due = {reloaders[channel] for channel in changed}
                    changed.clear()
                    for handler in due:
                        await handler()
                on_ready()
                wake.clear()
                try:
                    await asyncio.wait_for(wake.wait(), HEARTBEAT_S)
                except TimeoutError:
                    await driver.fetchval("SELECT 1", timeout=HEARTBEAT_TIMEOUT_S)
                if lost:
                    raise ConnectionLost("Notification connection closed")
        finally:
            for broadcast in broadcasts:
                broadcast.close()
            with contextlib.suppress(Exception):
                await connection.invalidate()


async def listen(
    engine: AsyncEngine, handlers: Mapping[str, Handler], on_lost: OnLost, stopping: asyncio.Event
) -> None:
    """Calls each channel's reloader after every (re)connect and after notifications on it, until `stopping` is set.

    Notifications that arrive while a reloader runs collapse into one more call. A lost connection, a failed heartbeat
    or a failed reloader calls `on_lost` (what the reloaders loaded may be stale from then on) and reconnects with
    exponential backoff; the reconnect calls every reloader again, so nothing sent while disconnected is missed.

    A broadcast gets every payload of its channel, in order, while the connection listens: it is opened once the
    connection listens and closed whenever the connection ends, which ends its subscriptions.
    """
    backoff = MIN_BACKOFF_S

    def on_ready() -> None:
        nonlocal backoff
        backoff = MIN_BACKOFF_S

    wake = asyncio.Event()
    relay = asyncio.create_task(_set_when(stopping, wake))
    try:
        while not stopping.is_set():
            try:
                await _listen_once(engine, handlers, wake, stopping, on_ready)
            except Exception:
                on_lost()
                log.exception("listen.failed", message="Listening failed, reconnecting", backoff_s=backoff)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stopping.wait(), backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_S)
    finally:
        relay.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await relay


def listen_worker(engine: AsyncEngine, handlers: Mapping[str, Handler], on_lost: OnLost) -> Worker:
    """The replica's one listening connection; `handlers` maps each channel to what it reloads or broadcasts to."""

    async def run(stopping: asyncio.Event) -> None:
        await listen(engine, handlers, on_lost, stopping)

    return Worker(name="listen", run=run)
