"""The counter flush loop: occurrence counters from Redis to the alert rows (SPEC §5.2, §9)."""

import asyncio
import contextlib

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.workers import WorkerLoop
from pagercutie.pipeline.dedup.stage import WindowStore, apply_counters

log = structlog.get_logger("dedup")

FLUSH_INTERVAL_S = 5.0
# Alerts per drain and per UPDATE.
BATCH = 500


async def flush_counters(
    sessionmaker: async_sessionmaker[AsyncSession], windows: WindowStore, batch: int = BATCH
) -> int:
    """Drain and apply counters until none are left; returns how many alerts were updated.

    A batch whose transaction fails goes back to Redis and the error propagates, so the next flush retries it.
    """
    flushed = 0
    while counters := await windows.drain(batch):
        try:
            async with sessionmaker() as session, session.begin():
                await apply_counters(session, counters)
        except BaseException:
            await windows.restore(counters)
            raise
        flushed += len(counters)
        if len(counters) < batch:
            break
    return flushed


def counter_flush(sessionmaker: async_sessionmaker[AsyncSession], windows: WindowStore) -> WorkerLoop:
    """The loop: a flush every `FLUSH_INTERVAL_S`, and a last one when the replica stops."""

    async def run(stopping: asyncio.Event) -> None:
        log.info("dedup.flush_started", interval_s=FLUSH_INTERVAL_S)
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stopping.wait(), FLUSH_INTERVAL_S)
            try:
                await flush_counters(sessionmaker, windows)
            except Exception:
                # The loop outlives a database outage; the counts stay in Redis until a flush commits.
                log.exception("dedup.flush_failed")
            if stopping.is_set():
                return

    return run
