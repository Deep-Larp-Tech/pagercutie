"""The executor loop: claims due step runs, runs them and completes them (SPEC §11.3)."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import assert_never

import structlog
from opentelemetry import propagate, trace
from opentelemetry.context import Context
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.listen import OnChange
from pagercutie.core.settings import Settings
from pagercutie.core.workers import WorkerLoop
from pagercutie.pipeline.executor.actions import Integrations
from pagercutie.pipeline.executor.outcomes import StepOutcome
from pagercutie.pipeline.executor.stage import (
    Act,
    Settle,
    StepJob,
    claim_due_steps,
    complete_step,
    plan_step,
    run_action,
    start_step,
)

log = structlog.get_logger("executor")
_tracer = trace.get_tracer("pagercutie.executor")

POLL_INTERVAL_S = 1.0
# Step runs in flight at once on one replica; a claim takes at most the free slots.
BATCH = 20
# After a failed pass the loop waits 2, 4, 8, … seconds, up to this, so a database outage logs a few errors a minute.
MAX_BACKOFF_S = 30.0

type Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ExecutorConfig:
    """The executor's limits, from `Settings` (ADR-0106, ADR-0109)."""

    lease: timedelta
    step_timeout_seconds: float
    max_errors: int

    @classmethod
    def from_settings(cls, settings: Settings) -> ExecutorConfig:
        return cls(
            lease=timedelta(seconds=settings.executor_lease_seconds),
            step_timeout_seconds=settings.executor_step_timeout_seconds,
            max_errors=settings.executor_step_max_errors,
        )


def _links(traceparent: str | None) -> list[trace.Link]:
    if traceparent is None:
        return []
    span_context = trace.get_current_span(propagate.extract({"traceparent": traceparent})).get_span_context()
    return [trace.Link(span_context)] if span_context.is_valid else []


async def execute(
    sessionmaker: async_sessionmaker[AsyncSession],
    integrations: Integrations,
    config: ExecutorConfig,
    job: StepJob,
    clock: Clock = _utc_now,
) -> None:
    """Plan one claimed step; for an action, mark it `running` in its own transaction, act, then complete it in
    another transaction.

    A failure is logged and the step is left to its lease; the next claim counts it in `errors` (ADR-0106).
    """
    # A root span: the loop runs under no request, and the ingest trace is a link, not a parent (SPEC §13).
    with _tracer.start_as_current_span(
        "executor.step",
        context=Context(),
        links=_links(job.traceparent),
        attributes={"run_id": str(job.run_id), "index": job.index, "action": job.step.action},
    ):
        try:
            outcome: StepOutcome
            plan = plan_step(job, config.max_errors)
            match plan:
                case Settle():
                    outcome = plan.outcome
                case Act():
                    async with sessionmaker() as session, session.begin():
                        started = await start_step(session, job, clock())
                    if started is None:
                        return
                    job = started.job
                    outcome = await run_action(job, plan, started.key, integrations, config.step_timeout_seconds)
                case _:
                    assert_never(plan)
            async with sessionmaker() as session, session.begin():
                await complete_step(session, job, outcome, clock())
        except Exception:
            log.exception("executor.step_failed", run_id=str(job.run_id), index=job.index)


async def _claim(
    sessionmaker: async_sessionmaker[AsyncSession], limit: int, config: ExecutorConfig, clock: Clock
) -> list[StepJob]:
    async with sessionmaker() as session, session.begin():
        return await claim_due_steps(session, limit, clock(), config.lease)


async def process_due(
    sessionmaker: async_sessionmaker[AsyncSession],
    integrations: Integrations,
    config: ExecutorConfig,
    clock: Clock = _utc_now,
) -> int:
    """Claim up to `BATCH` due step runs, run them to completion concurrently and return how many were claimed."""
    jobs = await _claim(sessionmaker, BATCH, config, clock)
    await asyncio.gather(*(execute(sessionmaker, integrations, config, job, clock) for job in jobs))
    return len(jobs)


def executor_loop(
    sessionmaker: async_sessionmaker[AsyncSession],
    integrations: Integrations,
    wake: asyncio.Event,
    config: ExecutorConfig,
) -> WorkerLoop:
    """The loop: a pass when `wake` is set (`steps_pending` notification), when a step finishes, or every
    `POLL_INTERVAL_S`; after a failed pass it backs off up to `MAX_BACKOFF_S`.

    Each claimed step runs as its own task, so a slow step holds only its own slot (ADR-0109); a pass claims as many
    steps as there are free slots. The poll finds steps whose delay ended and steps whose lease expired, which no
    notification announces. Stopping waits for the steps in flight, each bounded by the step timeout.
    """

    async def run(stopping: asyncio.Event) -> None:
        log.info("executor.started", poll_interval_s=POLL_INTERVAL_S, batch=BATCH)
        in_flight: set[asyncio.Task[None]] = set()
        failed_passes = 0
        while not stopping.is_set():
            delay = POLL_INTERVAL_S if failed_passes == 0 else min(2.0**failed_passes, MAX_BACKOFF_S)
            await _wait(wake, stopping, in_flight, delay)
            wake.clear()
            if stopping.is_set():
                break
            try:
                while (free := BATCH - len(in_flight)) > 0 and not stopping.is_set():
                    jobs = await _claim(sessionmaker, free, config, _utc_now)
                    for job in jobs:
                        task = asyncio.create_task(execute(sessionmaker, integrations, config, job))
                        in_flight.add(task)
                        task.add_done_callback(in_flight.discard)
                    if len(jobs) < free:
                        break
                failed_passes = 0
            except Exception:
                # The loop outlives a database outage; due steps stay in the table.
                failed_passes += 1
                log.exception("executor.loop_failed", failed_passes=failed_passes)
        await asyncio.gather(*in_flight)

    return run


async def _wait(wake: asyncio.Event, stopping: asyncio.Event, in_flight: set[asyncio.Task[None]], delay: float) -> None:
    """Until `wake` or `stopping` is set, a step in flight finishes, or `delay` seconds pass."""
    signals = [asyncio.create_task(wake.wait()), asyncio.create_task(stopping.wait())]
    try:
        await asyncio.wait([*signals, *in_flight], timeout=delay, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for signal in signals:
            signal.cancel()


def steps_pending_handler(wake: asyncio.Event) -> OnChange:
    """The `steps_pending` handler: wakes the loop."""

    async def handler() -> None:
        wake.set()

    return handler
