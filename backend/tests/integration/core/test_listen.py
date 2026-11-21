import asyncio
import uuid
from collections.abc import AsyncIterator, Callable

import anyio
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from pagercutie.core import listen as listen_module
from pagercutie.core.listen import listen

pytestmark = pytest.mark.anyio


class Recorder:
    """Counts handler calls and `on_lost` calls; `fail_first` makes the first handler call raise."""

    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self.lost = 0
        self.fail_first = fail_first
        self.changed = asyncio.Event()

    async def handler(self) -> None:
        self.calls += 1
        self.changed.set()
        if self.fail_first and self.calls == 1:
            raise ValueError("first load fails")

    def on_lost(self) -> None:
        self.lost += 1

    async def wait_for(self, condition: Callable[[], bool]) -> None:
        with anyio.fail_after(5):
            while not condition():
                self.changed.clear()
                await self.changed.wait()


@pytest.fixture
def channel() -> str:
    return f"test_{uuid.uuid4().hex}"


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(listen_module, "MIN_BACKOFF_S", 0.05)


@pytest.fixture
async def running(engine: AsyncEngine, channel: str) -> AsyncIterator[Callable[[Recorder], None]]:
    stopping = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []

    def start(recorder: Recorder) -> None:
        tasks.append(asyncio.create_task(listen(engine, {channel: recorder.handler}, recorder.on_lost, stopping)))

    yield start
    stopping.set()
    with anyio.fail_after(5):
        await asyncio.gather(*tasks)


async def notify(engine: AsyncEngine, channel: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(select(func.pg_notify(channel, "")))


async def test_handler_runs_on_connect_and_after_each_notification(
    engine: AsyncEngine, channel: str, running: Callable[[Recorder], None]
) -> None:
    recorder = Recorder()
    running(recorder)
    await recorder.wait_for(lambda: recorder.calls == 1)

    await notify(engine, channel)

    await recorder.wait_for(lambda: recorder.calls == 2)
    assert recorder.lost == 0


async def test_lost_connection_calls_on_lost_and_reloads_after_reconnecting(
    engine: AsyncEngine, channel: str, running: Callable[[Recorder], None]
) -> None:
    recorder = Recorder()
    running(recorder)
    await recorder.wait_for(lambda: recorder.calls == 1)

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE :listen"),
            {"listen": f'LISTEN "{channel}"%'},
        )

    await recorder.wait_for(lambda: recorder.calls == 2)
    assert recorder.lost == 1


async def test_failed_handler_calls_on_lost_and_is_retried(channel: str, running: Callable[[Recorder], None]) -> None:
    recorder = Recorder(fail_first=True)
    running(recorder)

    await recorder.wait_for(lambda: recorder.calls == 2)
    assert recorder.lost == 1


async def test_heartbeats_keep_the_connection_without_reloading(
    monkeypatch: pytest.MonkeyPatch, running: Callable[[Recorder], None]
) -> None:
    monkeypatch.setattr(listen_module, "HEARTBEAT_S", 0.02)
    recorder = Recorder()
    running(recorder)
    await recorder.wait_for(lambda: recorder.calls == 1)

    await asyncio.sleep(0.2)

    assert (recorder.calls, recorder.lost) == (1, 0)
