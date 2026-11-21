import asyncio
import contextlib
import time
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
from pagercutie.pipeline.dispatch.stage import (
    ChannelAdapter,
    DeliveryJob,
    Throttle,
    claim_due,
    complete,
    record_latency,
    send,
)

log = structlog.get_logger("dispatch")
_tracer = trace.get_tracer("pagercutie.dispatch")

# Retries and throttled deliveries have no `NOTIFY`, so the loop also claims this often (SPEC §10).
POLL_SECONDS = 1.0
# Sends in flight at once. The loop claims only as many rows as there are free slots, so no claimed row waits with its
# lease running; a queued row could outlive the lease behind slow sends and be sent again by another replica (ADR-0084).
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


async def _deliver(context: DispatchContext, job: DeliveryJob) -> None:
    """Send one claimed delivery and record the result in its own transaction."""
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
                received = await complete(
                    session,
                    job,
                    result,
                    datetime.now(UTC),
                    timedelta(seconds=context.settings.throttle_refill_seconds),
                )
            # After the commit, which sends a UI delivery's `alert_changed`, so the latency includes it (SPEC §13).
            record_latency(job.channel, received, datetime.now(UTC))
    except Exception:
        # The lease expires and another claim sends the delivery again (SPEC §5.4).
        log.exception("dispatch.failed", message="Completing a delivery failed", delivery_id=str(job.delivery_id))


def claim_limit(settings: Settings) -> int:
    """Sends in flight at once, and so the most rows claimed: `delivery_batch_size`, at most `MAX_CONCURRENT_SENDS`."""
    return min(settings.delivery_batch_size, MAX_CONCURRENT_SENDS)


async def _claim(context: DispatchContext, limit: int) -> list[DeliveryJob]:
    async with context.sessionmaker() as session, session.begin():
        return await claim_due(
            session, limit, datetime.now(UTC), timedelta(seconds=context.settings.delivery_lease_seconds)
        )


async def _sleep(
    stopping: asyncio.Event, wake: asyncio.Event | None, sends: set[asyncio.Task[None]], seconds: float | None
) -> None:
    """Return when `stopping` or `wake` is set, a task in `sends` finishes, or `seconds` pass (None: no limit)."""
    waiters = {asyncio.create_task(stopping.wait())}
    if wake is not None:
        waiters.add(asyncio.create_task(wake.wait()))
    try:
        await asyncio.wait({*waiters, *sends}, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            waiter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*waiters)


async def dispatch_loop(context: DispatchContext, stopping: asyncio.Event) -> None:
    """Keep up to `claim_limit` sends in flight until `stopping` is set, then wait for them (SPEC §10, ADR-0102).

    The loop claims as many rows as there are free slots after `NOTIFY deliveries_pending` set `context.wake`, after
    the poll interval passed, or when the previous claim filled every free slot and a slot has freed since.
    """
    log.info("dispatch.started", message="Dispatcher started")
    limit = claim_limit(context.settings)
    in_flight: set[asyncio.Task[None]] = set()
    claim_now = True
    next_poll = time.monotonic()
    try:
        while not stopping.is_set():
            free = limit - len(in_flight)
            if free > 0 and claim_now:
                # Cleared before the claim: a notification that arrives during it triggers the next claim.
                context.wake.clear()
                next_poll = time.monotonic() + POLL_SECONDS
                try:
                    jobs = await _claim(context, free)
                except Exception:
                    log.exception("dispatch.failed", message="Claiming deliveries failed, retrying")
                    jobs = []
                for job in jobs:
                    task = asyncio.create_task(_deliver(context, job))
                    in_flight.add(task)
                    task.add_done_callback(in_flight.discard)
                # A claim that filled every free slot may have left due rows behind.
                claim_now = len(jobs) == free
                continue
            if free > 0:
                await _sleep(stopping, context.wake, set(), max(0.0, next_poll - time.monotonic()))
            else:
                # The wake stays set while every slot is busy; the claim after the next free slot consumes it.
                await _sleep(stopping, None, in_flight, None)
            claim_now = claim_now or context.wake.is_set() or time.monotonic() >= next_poll
    finally:
        # Each send completes its row, so stopping or a cancelled loop leaves no row leased by an abandoned send.
        if in_flight:
            await asyncio.wait(in_flight)


def dispatch_worker(context: DispatchContext) -> Worker:
    """The replica's dispatch loop as a `Worker`; the factory carries the context a bare `run(stopping)` could not."""

    async def run(stopping: asyncio.Event) -> None:
        await dispatch_loop(context, stopping)

    return Worker(name="dispatch", run=run)
