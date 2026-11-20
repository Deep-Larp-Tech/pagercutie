import asyncio
import signal

import pytest

from pagercutie.core.workers import Worker, run_workers

pytestmark = pytest.mark.anyio


async def test_workers_run_until_the_group_exits() -> None:
    stopped: list[str] = []

    async def loop(stopping: asyncio.Event) -> None:
        await stopping.wait()
        stopped.append("loop")

    async with run_workers([Worker(name="loop", run=loop)]) as group:
        await asyncio.sleep(0)
        assert stopped == []

    assert stopped == ["loop"]
    assert not group.failed


async def test_a_failed_worker_marks_the_group_and_shuts_the_process_down(monkeypatch: pytest.MonkeyPatch) -> None:
    raised: list[signal.Signals] = []
    monkeypatch.setattr(signal, "raise_signal", raised.append)

    async def crash(_: asyncio.Event) -> None:
        raise RuntimeError("boom")

    async with run_workers([Worker(name="crash", run=crash)]) as group:
        await asyncio.sleep(0.01)

    assert group.failed
    assert raised == [signal.SIGTERM]
