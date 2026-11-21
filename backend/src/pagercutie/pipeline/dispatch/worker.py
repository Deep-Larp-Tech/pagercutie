import asyncio
import contextlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from opentelemetry import propagate, trace
from opentelemetry.context import Context
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.enums import Channel
from pagercutie.core.settings import Settings
from pagercutie.core.workers import Worker
from pagercutie.pipeline.dispatch.stage import ChannelAdapter, DeliveryJob, Throttle, claim_due, complete, send

log = structlog.get_logger("dispatch")
_tracer = trace.get_tracer("pagercutie.dispatch")

# Retries and throttled deliveries have no `NOTIFY`, so the loop also polls this often (SPEC §10).
POLL_SECONDS = 1.0
# Sends running at once. Jobs wait for a slot with their lease running, so this stays well under a batch's worth of
# slow sends per lease.
MAX_CONCURRENT_SENDS = 16


@dataclass(frozen=True)
class DispatchContext:
    """What the dispatch loop of one replica needs; built once at startup (no module globals)."""

    sessionmaker: async_sessionmaker[AsyncSession]
    adapters: Mapping[Channel, ChannelAdapter]
    throttle: Throttle
    settings: Settings
    # Set on `NOTIFY deliveries_pending`, so a new delivery does not wait for the next poll (NFR-3).
    wake: asyncio.Event


def _links(traceparent: str | None) -> list[trace.Link]:
    if traceparent is None:
        return []
    span_context = trace.get_current_span(propagate.extract({"traceparent": traceparent})).get_span_context()
    return [trace.Link(span_context)] if span_context.is_valid else []


async def _deliver(context: DispatchContext, job: DeliveryJob, slots: asyncio.Semaphore) -> None:
    """Send one claimed delivery and record the result in its own transaction."""
    async with slots:
        try:
            # A root span: the loop runs under no request, and the ingest trace is a link, not a parent.
            with _tracer.start_as_current_span(
                "dispatch.send",
                context=Context(),
                links=_links(job.traceparent),
                attributes={"delivery_id": str(job.delivery_id), "alert_id": str(job.alert_id), "channel": job.channel},
            ):
                result = await send(job, context.adapters, context.throttle)
                async with context.sessionmaker() as session, session.begin():
                    await complete(
                        session,
                        job,
                        result,
                        datetime.now(UTC),
                        timedelta(seconds=context.settings.throttle_refill_seconds),
                    )
        except Exception:
            # The lease expires and another claim sends the delivery again (SPEC §5.4).
            log.exception("dispatch.failed", message="Completing a delivery failed", delivery_id=str(job.delivery_id))


async def dispatch_once(context: DispatchContext) -> bool:
    """Claim one batch, send it and record the results. True when the batch was full, so more may be due."""
    limit = context.settings.delivery_batch_size
    async with context.sessionmaker() as session, session.begin():
        jobs = await claim_due(
            session, limit, datetime.now(UTC), timedelta(seconds=context.settings.delivery_lease_seconds)
        )
    slots = asyncio.Semaphore(MAX_CONCURRENT_SENDS)
    await asyncio.gather(*(_deliver(context, job, slots) for job in jobs))
    return len(jobs) >= limit


async def _sleep_until_woken(wake: asyncio.Event, stopping: asyncio.Event) -> None:
    waiting = {asyncio.create_task(wake.wait()), asyncio.create_task(stopping.wait())}
    try:
        await asyncio.wait(waiting, timeout=POLL_SECONDS, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in waiting:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*waiting)


async def dispatch_loop(context: DispatchContext, stopping: asyncio.Event) -> None:
    """Claim, send and complete due deliveries until `stopping` is set; wakes on `NOTIFY deliveries_pending`."""
    log.info("dispatch.started", message="Dispatcher started")
    while not stopping.is_set():
        # Cleared before the claim: a notification that arrives during it makes the next wait return at once.
        context.wake.clear()
        try:
            if await dispatch_once(context):
                continue
        except Exception:
            log.exception("dispatch.failed", message="Dispatch iteration failed, retrying")
        await _sleep_until_woken(context.wake, stopping)


def dispatch_worker(context: DispatchContext) -> Worker:
    """The replica's dispatch loop as a `Worker`; the factory carries the context a bare `run(stopping)` could not."""

    async def run(stopping: asyncio.Event) -> None:
        await dispatch_loop(context, stopping)

    return Worker(name="dispatch", run=run)


async def run(stopping: asyncio.Event) -> None:
    """Placeholder that `main.WORKERS` still registers; chunk G replaces it with `dispatch_worker`."""
    log.info("dispatch.started", message="Dispatcher not wired to a DispatchContext yet; sending is disabled")
    await stopping.wait()
