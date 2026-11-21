"""Background loops run by every backend replica for the lifetime of the app."""

import asyncio
import signal
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass

import structlog

log = structlog.get_logger("workers")

type WorkerLoop = Callable[[asyncio.Event], Awaitable[None]]


@dataclass(frozen=True)
class Worker:
    """A loop that runs until the event it is given is set, then returns."""

    name: str
    run: WorkerLoop


@dataclass
class WorkerGroup:
    """`failed` is set when a worker stopped on its own; the process then shuts down and the container restarts."""

    failed: bool = False


@asynccontextmanager
async def run_workers(workers: Sequence[Worker]) -> AsyncGenerator[WorkerGroup]:
    group = WorkerGroup()
    stopping = asyncio.Event()

    def on_done(name: str, task: asyncio.Task[None]) -> None:
        error = None if task.cancelled() else task.exception()
        if stopping.is_set():
            if error:
                log.error("workers.failed", message="Worker failed while stopping", worker=name, exc_info=error)
            return
        group.failed = True
        log.error("workers.stopped", message="Worker stopped unexpectedly, shutting down", worker=name, exc_info=error)
        signal.raise_signal(signal.SIGTERM)

    tasks: list[asyncio.Task[None]] = []
    for worker in workers:
        task = asyncio.create_task(_as_coroutine(worker.run, stopping), name=worker.name)
        task.add_done_callback(lambda done, name=worker.name: on_done(name, done))
        tasks.append(task)
    try:
        yield group
    finally:
        stopping.set()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _as_coroutine(run: WorkerLoop, stopping: asyncio.Event) -> None:
    await run(stopping)
