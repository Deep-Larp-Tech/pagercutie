"""Reacting to Postgres `NOTIFY` signals between replicas, over one connection per replica (SPEC §5.3, ADR-0063)."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping

import asyncpg
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from pagercutie.core.workers import Worker

log = structlog.get_logger("listen")

MIN_BACKOFF_S = 0.5
MAX_BACKOFF_S = 30.0
# A half-open connection never reports its loss; a query every HEARTBEAT_S finds it.
HEARTBEAT_S = 10.0
HEARTBEAT_TIMEOUT_S = 5.0

type OnChange = Callable[[], Awaitable[None]]
type OnLost = Callable[[], None]


class ConnectionLost(Exception):
    """Postgres closed the listening connection."""


async def _set_when(source: asyncio.Event, target: asyncio.Event) -> None:
    await source.wait()
    target.set()


async def _listen_once(
    engine: AsyncEngine,
    handlers: Mapping[str, OnChange],
    wake: asyncio.Event,
    stopping: asyncio.Event,
    on_ready: Callable[[], None],
) -> None:
    """Serves one connection until `stopping` is set; raises when the connection is lost or a handler fails."""
    changed: set[str] = set(handlers)
    lost = False

    def on_notification(_connection: object, _pid: int, channel: str, _payload: str) -> None:
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
            log.info("listen.connected", message="Listening for notifications", channels=sorted(handlers))
            # Every handler runs once per (re)connect, covering notifications sent while disconnected.
            while not stopping.is_set():
                while changed:
                    # Channels sharing a handler (e.g. one cache fed by two tables) run it once.
                    due = {handlers[channel] for channel in changed}
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
            # Discarded instead of returned to the pool, where it would stay subscribed to the channels.
            with contextlib.suppress(Exception):
                await connection.invalidate()


async def listen(
    engine: AsyncEngine, handlers: Mapping[str, OnChange], on_lost: OnLost, stopping: asyncio.Event
) -> None:
    """Calls each channel's handler after every (re)connect and after notifications on it, until `stopping` is set.

    Notifications that arrive while a handler runs collapse into one more call. A lost connection, a failed heartbeat
    or a failed handler calls `on_lost` (what the handlers loaded may be stale from then on) and reconnects with
    exponential backoff; the reconnect calls every handler again, so nothing sent while disconnected is missed.
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
            # Any failure, not only connection errors: a crashed listener would take the replica down with it.
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


def listen_worker(engine: AsyncEngine, handlers: Mapping[str, OnChange], on_lost: OnLost) -> Worker:
    """The replica's one listening connection; `handlers` maps each channel to what it reloads."""

    async def run(stopping: asyncio.Event) -> None:
        await listen(engine, handlers, on_lost, stopping)

    return Worker(name="listen", run=run)
