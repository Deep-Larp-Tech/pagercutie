"""The executor loop: claims due step runs, runs them and completes them (SPEC §11.3)."""

import asyncio
import contextlib
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.listen import OnChange
from pagercutie.core.workers import WorkerLoop
from pagercutie.pipeline.executor.actions import Integrations
from pagercutie.pipeline.executor.stage import StepJob, claim_due_steps, complete_step, run_step

log = structlog.get_logger("executor")

POLL_INTERVAL_S = 1.0
# Step runs claimed per pass; they run concurrently.
BATCH = 20


async def _execute(sessionmaker: async_sessionmaker[AsyncSession], integrations: Integrations, job: StepJob) -> None:
    """Run one claimed step and complete it in its own transaction.

    A failure is logged and the step is left to its lease, which expires and runs it again (ADR-0008).
    """
    try:
        outcome = await run_step(job, integrations)
        async with sessionmaker() as session, session.begin():
            await complete_step(session, job, outcome, now=datetime.now(UTC))
    except Exception:
        log.exception("executor.step_failed", run_id=str(job.run_id), index=job.index)


async def process_due(sessionmaker: async_sessionmaker[AsyncSession], integrations: Integrations, now: datetime) -> int:
    """Claim up to `BATCH` due step runs, run them concurrently and return how many were claimed."""
    async with sessionmaker() as session, session.begin():
        jobs = await claim_due_steps(session, BATCH, now)
    await asyncio.gather(*(_execute(sessionmaker, integrations, job) for job in jobs))
    return len(jobs)


def executor_loop(
    sessionmaker: async_sessionmaker[AsyncSession], integrations: Integrations, wake: asyncio.Event
) -> WorkerLoop:
    """The loop: a pass when `wake` is set (`steps_pending` notification) or every `POLL_INTERVAL_S`.

    Stopping takes at most one poll interval.
    The poll finds steps whose delay ended and steps whose lease expired, which no notification announces.
    """

    async def run(stopping: asyncio.Event) -> None:
        log.info("executor.started", poll_interval_s=POLL_INTERVAL_S, batch=BATCH)
        while not stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wake.wait(), POLL_INTERVAL_S)
            wake.clear()
            try:
                while await process_due(sessionmaker, integrations, datetime.now(UTC)) == BATCH:
                    if stopping.is_set():
                        break
            except Exception:
                # The loop outlives a database outage; due steps stay in the table.
                log.exception("executor.loop_failed")

    return run


def steps_pending_handler(wake: asyncio.Event) -> OnChange:
    """The `steps_pending` handler: wakes the loop."""

    async def handler() -> None:
        wake.set()

    return handler
