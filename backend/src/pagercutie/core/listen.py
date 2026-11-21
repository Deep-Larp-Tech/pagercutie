"""Reacting to Postgres `NOTIFY` signals between replicas, over one connection per replica (SPEC §5.3)."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping

import asyncpg
import structlog
from sqlalchemy import make_url
from sqlalchemy.exc import SQLAlchemyError

from pagercutie.core.settings import Settings
from pagercutie.core.workers import Worker

log = structlog.get_logger("listen")

MIN_BACKOFF_S = 0.5
MAX_BACKOFF_S = 30.0
CLOSE_TIMEOUT_S = 5.0

type OnChange = Callable[[], Awaitable[None]]


def asyncpg_dsn(database_url: str) -> str:
    """The SQLAlchemy URL (`postgresql+asyncpg://…`) as a plain DSN asyncpg accepts."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


async def _wait_any(*events: asyncio.Event) -> None:
    waiters = [asyncio.create_task(event.wait()) for event in events]
    try:
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            waiter.cancel()


async def _sleep_unless_stopping(stopping: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stopping.wait(), seconds)


_CONNECTION_ERRORS = (OSError, asyncpg.PostgresError, asyncpg.InterfaceError)


async def _listen_once(dsn: str, handlers: Mapping[str, OnChange], stopping: asyncio.Event) -> bool:
    """Serves one connection until it is lost or `stopping` is set; True once every handler succeeded."""
    changed: set[str] = set(handlers)
    wake = asyncio.Event()
    lost = asyncio.Event()
    succeeded = False

    def on_notification(_connection: object, _pid: int, channel: str, _payload: str) -> None:
        changed.add(channel)
        wake.set()

    connection = await asyncpg.connect(dsn)
    try:
        connection.add_termination_listener(lambda _: lost.set())
        for channel in handlers:
            await connection.add_listener(channel, on_notification)
        log.info("listen.connected", message="Listening for notifications", channels=sorted(handlers))
        # Every handler runs once per (re)connect, covering notifications sent while disconnected.
        wake.set()
        while not (stopping.is_set() or lost.is_set()):
            wake.clear()
            while changed:
                # Channels sharing a handler (e.g. one cache fed by two tables) run it once.
                due = {handlers[channel] for channel in changed}
                changed.clear()
                for handler in due:
                    await handler()
            succeeded = True
            await _wait_any(wake, lost, stopping)
        if lost.is_set():
            log.warning("listen.connection_lost", message="Notification connection lost")
        return succeeded
    finally:
        if lost.is_set():
            connection.terminate()
        else:
            with contextlib.suppress(*_CONNECTION_ERRORS, TimeoutError):
                await connection.close(timeout=CLOSE_TIMEOUT_S)


async def listen(settings: Settings, handlers: Mapping[str, OnChange], stopping: asyncio.Event) -> None:
    """Calls each channel's handler after every (re)connect and after notifications on it, until `stopping` is set.

    Notifications that arrive while a handler runs collapse into one more call. A lost connection or a failed
    handler reconnects with exponential backoff, and the reconnect calls every handler again, so nothing sent while
    disconnected is missed.
    """
    dsn = asyncpg_dsn(settings.database_url)
    backoff = MIN_BACKOFF_S
    while not stopping.is_set():
        try:
            if await _listen_once(dsn, handlers, stopping):
                backoff = MIN_BACKOFF_S
        except (*_CONNECTION_ERRORS, SQLAlchemyError):
            log.exception("listen.failed", message="Listening failed, reconnecting", backoff_s=backoff)
        if not stopping.is_set():
            await _sleep_unless_stopping(stopping, backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_S)


def listen_worker(settings: Settings, handlers: Mapping[str, OnChange]) -> Worker:
    """The replica's one listening connection; `handlers` maps each channel to what it reloads."""

    async def run(stopping: asyncio.Event) -> None:
        await listen(settings, handlers, stopping)

    return Worker(name="listen", run=run)
