"""Entrypoints of the dispatch stage, called by its loop in every replica (`worker.py`)."""

import asyncio
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, assert_never

import structlog
from sqlalchemy import ColumnElement, and_, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pagercutie.alerts.models import Alert, Delivery
from pagercutie.alerts.schemas import AlertStatus, DeliveryStatus
from pagercutie.core.enums import Channel
from pagercutie.pipeline.dispatch import state
from pagercutie.pipeline.dispatch.digest import (
    Merged,
    detach_late_members,
    digest_message,
    load_digests,
    merge_into_digest,
)
from pagercutie.pipeline.dispatch.fallback import Failed, FallbackOutcome, fall_back

log = structlog.get_logger("dispatch")

MAX_BACKOFF_SECONDS = 300
ALERT_RESOLVED = "Alert resolved before the delivery was sent"
DIGEST_EMPTIED = "Every delivery in the digest was cancelled"


@dataclass(frozen=True)
class Single:
    """A delivery for one alert."""


@dataclass(frozen=True)
class Digest:
    """A digest delivery (ADR-0081); `member_ids` are the members its message lists, read when it was claimed."""

    member_ids: frozenset[uuid.UUID]


type JobKind = Single | Digest


@dataclass(frozen=True)
class DeliveryJob:
    """A `pending` delivery leased to this replica by `claim_due`."""

    delivery_id: uuid.UUID
    alert_id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    # Rendered for the channel when routing created the delivery; for a digest, composed from `kind.member_ids`.
    message: str
    # Earlier send attempts; the basis of the retry backoff.
    attempts: int
    # End of this claim's lease. `complete` only writes while the row still holds this value, so a replica whose
    # lease expired cannot overwrite the replica that claimed the row after it (SPEC §10).
    lease_until: datetime
    # W3C trace context of the ingest request; the send span links to it (SPEC §13).
    traceparent: str | None = None
    kind: JobKind = Single()


@dataclass(frozen=True)
class Sent:
    at: datetime


@dataclass(frozen=True)
class SendFailed:
    """The channel adapter failed; the delivery is retried with backoff (DEL-5) unless the failure is permanent."""

    error: str
    # The send can never succeed as configured, e.g. the user has no phone number; no retry is scheduled.
    permanent: bool = False


@dataclass(frozen=True)
class Throttled:
    """The recipient's token bucket is empty; the delivery joins their next digest (SPEC §9)."""


type SendResult = Sent | SendFailed | Throttled


@dataclass(frozen=True)
class Delivered:
    """`complete` marked the delivery, and a digest's listed members, `sent`."""

    channel: Channel
    # Seconds from each carried event's ingest to the send: one per member for a digest (SPEC §13).
    latencies_s: tuple[float, ...]


@dataclass(frozen=True)
class RetryScheduled:
    """`complete` marked the delivery `failed` with a `retry_at`."""

    channel: Channel


@dataclass(frozen=True)
class GaveUp:
    """`complete` marked the delivery `undeliverable`, with its listed members for a digest, and tried a fallback for
    each (ADR-0110)."""

    channel: Channel
    fallbacks: tuple[FallbackOutcome, ...]


@dataclass(frozen=True)
class Postponed:
    """`complete` left the throttled delivery `pending` until the next token; `merged` when it joined a digest."""

    channel: Channel
    merged: Merged | None


@dataclass(frozen=True)
class LeaseLost:
    """Another replica owns the delivery now; the result was dropped."""

    channel: Channel


type Completion = Delivered | RetryScheduled | GaveUp | Postponed | LeaseLost


class ChannelAdapter(Protocol):
    """Sends deliveries on one channel; replacing a simulated provider touches only its adapter (DEL-4)."""

    async def send(self, job: DeliveryJob) -> Sent | SendFailed:
        """Send `job.message` to `job.user_id`. Returns `SendFailed` for provider errors instead of raising."""
        ...


class Throttle(Protocol):
    """Per-recipient token buckets shared by every replica; the Redis implementation (SPEC §5.2)."""

    async def allow(self, user_id: uuid.UUID) -> bool:
        """Take one token for `user_id`. True when Redis cannot be reached: throttling fails open."""
        ...

    async def refund(self, user_id: uuid.UUID) -> None:
        """Give back the token of a send that failed, never above the bucket's capacity (ADR-0109)."""
        ...


def retry_delay(attempts: int) -> timedelta:
    """Backoff after `attempts` earlier attempts: 1 s, 2 s, 4 s, … capped at 5 minutes (DEL-5)."""
    return timedelta(seconds=min(2 ** min(attempts, 16), MAX_BACKOFF_SECONDS))


def is_throttled_channel(channel: Channel) -> bool:
    """The UI channel is a feed row; throttling it would hide alerts from the live feed."""
    match channel:
        case Channel.EMAIL | Channel.SMS | Channel.PHONE:
            return True
        case Channel.UI:
            return False
        case _:
            assert_never(channel)


async def cancel_for_resolved_alerts(session: AsyncSession, now: datetime, limit: int) -> list[Channel]:
    """Cancel up to `limit` unsent deliveries whose alert is resolved; returns the channel of each (ADR-0110).

    Digest members are cancelled one by one; a digest itself is cancelled by `claim_due` once it carries no member.
    Rows another replica holds are skipped. The caller commits.
    """
    member = aliased(Delivery)
    cancellable = (
        select(Delivery.id)
        .where(
            state.unsent(now),
            exists().where(Alert.id == Delivery.alert_id, Alert.status == AlertStatus.RESOLVED),
            ~exists().where(member.digest_id == Delivery.id),
        )
        .limit(limit)
        .with_for_update(skip_locked=True, of=Delivery)
        .cte("cancellable")
        .prefix_with("MATERIALIZED")
    )
    cancelled = await session.scalars(
        update(Delivery)
        .where(Delivery.id.in_(select(cancellable.c.id)))
        .values(status=DeliveryStatus.CANCELLED, retry_at=None, lease_until=None, last_error=ALERT_RESOLVED)
        .returning(Delivery.channel)
        .execution_options(synchronize_session=False)
    )
    return list(cancelled)


async def claim_due(session: AsyncSession, limit: int, now: datetime, lease: timedelta) -> list[DeliveryJob]:
    """Lease up to `limit` due deliveries with `FOR UPDATE SKIP LOCKED` (SPEC §10); the caller commits.

    Due is `state.due`. A claimed digest gets its message composed from the members it carries now, and the job
    remembers them, so completion marks exactly the members the sent message listed; a digest left without members
    is cancelled instead.
    """
    lease_until = now + lease
    # MATERIALIZED: the planner must run the locking subquery once, or the UPDATE could touch more than `limit` rows.
    claimable = (
        select(Delivery.id)
        .where(state.due(now))
        .order_by(Delivery.created_at, Delivery.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .cte("claimable")
        .prefix_with("MATERIALIZED")
    )
    claimed = (
        await session.execute(
            update(Delivery)
            .where(Delivery.id.in_(select(claimable.c.id)))
            .values(lease_until=lease_until)
            .returning(
                Delivery.id,
                Delivery.alert_id,
                Delivery.user_id,
                Delivery.channel,
                Delivery.message,
                Delivery.attempts,
                Delivery.traceparent,
                Delivery.created_at,
            )
            .execution_options(synchronize_session=False)
        )
    ).all()
    rows = sorted(claimed, key=lambda row: (row.created_at, row.id))
    digests = await load_digests(session, [row.id for row in rows])
    jobs: list[DeliveryJob] = []
    emptied: list[uuid.UUID] = []
    for row in rows:
        kind: JobKind = Single()
        message = row.message
        if row.id in digests.ids:
            members = digests.pending.get(row.id, [])
            if not members:
                emptied.append(row.id)
                continue
            kind = Digest(member_ids=frozenset(member.id for member in members))
            message = digest_message([member.message for member in members])
            if message != row.message:
                await session.execute(
                    update(Delivery)
                    .where(Delivery.id == row.id)
                    .values(message=message)
                    .execution_options(synchronize_session=False)
                )
        jobs.append(
            DeliveryJob(
                delivery_id=row.id,
                alert_id=row.alert_id,
                user_id=row.user_id,
                channel=row.channel,
                message=message,
                attempts=row.attempts,
                lease_until=lease_until,
                traceparent=row.traceparent,
                kind=kind,
            )
        )
    if emptied:
        await session.execute(
            update(Delivery)
            .where(Delivery.id.in_(emptied))
            .values(status=DeliveryStatus.CANCELLED, retry_at=None, lease_until=None, last_error=DIGEST_EMPTIED)
            .execution_options(synchronize_session=False)
        )
    return jobs


async def send(
    job: DeliveryJob, adapters: Mapping[Channel, ChannelAdapter], throttle: Throttle, timeout_s: float
) -> SendResult:
    """Throttle, then send through the adapter for `job.channel` within `timeout_s`. Runs outside any transaction.

    A send that took a token and failed gives it back (ADR-0109). A send slower than `timeout_s` is a transient
    failure; its lease is still running, so no other replica has sent it meanwhile (ADR-0110).
    """
    took_token = False
    result: Sent | SendFailed
    try:
        if is_throttled_channel(job.channel):
            if not await throttle.allow(job.user_id):
                return Throttled()
            took_token = True
        async with asyncio.timeout(timeout_s):
            result = await adapters[job.channel].send(job)
    except TimeoutError:
        result = SendFailed(error=f"Send timed out after {timeout_s:g} s")
    except Exception as error:
        # The Protocol asks adapters to return failures, but a bug in one must not stop the loop or the other sends.
        log.exception(
            "dispatch.send_raised",
            message="Channel adapter raised instead of returning a failure",
            delivery_id=str(job.delivery_id),
            channel=job.channel,
        )
        result = SendFailed(error=f"{type(error).__name__}: {error}")
    if took_token and isinstance(result, SendFailed):
        await throttle.refund(job.user_id)
    return result


async def complete(
    session: AsyncSession, job: DeliveryJob, result: SendResult, now: datetime, throttle_refill: timedelta
) -> Completion:
    """Record the result and end the lease (DEL-6); returns what changed, for the metrics.

    `Sent` marks the delivery `sent`; a transient `SendFailed` marks it `failed` with `retry_at`; a permanent one marks
    it `undeliverable` and falls back to the recipient's next channel; `Throttled` leaves it `pending` until the
    recipient's bucket holds a token again (`throttle_refill`) and merges it into a digest. Writes only while the row
    still holds `job.lease_until`; otherwise another replica owns the delivery and the result is dropped.
    """
    match result:
        case Sent():
            return await _complete_sent(session, job, result)
        case SendFailed() if result.permanent:
            return await _complete_permanent(session, job, result)
        case SendFailed():
            return await _complete_retry(session, job, result, now)
        case Throttled():
            return await _complete_throttled(session, job, now, throttle_refill)
        case _:
            assert_never(result)


def _owned(job: DeliveryJob) -> ColumnElement[bool]:
    return and_(Delivery.id == job.delivery_id, Delivery.lease_until == job.lease_until)


def _lease_lost(job: DeliveryJob) -> LeaseLost:
    log.warning(
        "dispatch.lease_lost",
        message="Delivery lease expired and another replica took over; dropping this result",
        delivery_id=str(job.delivery_id),
    )
    return LeaseLost(channel=job.channel)


def _listed(job: DeliveryJob) -> frozenset[uuid.UUID]:
    match job.kind:
        case Single():
            return frozenset()
        case Digest(member_ids=member_ids):
            return member_ids
        case _:
            assert_never(job.kind)


async def _complete_sent(session: AsyncSession, job: DeliveryJob, result: Sent) -> Completion:
    received_at = await session.scalar(
        update(Delivery)
        .where(_owned(job))
        .values(
            status=DeliveryStatus.SENT,
            sent_at=result.at,
            attempts=Delivery.attempts + 1,
            retry_at=None,
            lease_until=None,
            last_error=None,
        )
        .returning(Delivery.received_at)
        .execution_options(synchronize_session=False)
    )
    if received_at is None:
        return _lease_lost(job)
    received = [received_at]
    if listed := _listed(job):
        # A digest carries its members: each waited since its own event, not since the digest row was created.
        received = list(
            await session.scalars(
                update(Delivery)
                .where(Delivery.id.in_(listed), Delivery.status == DeliveryStatus.PENDING)
                .values(status=DeliveryStatus.SENT, sent_at=result.at, last_error=None)
                .returning(Delivery.received_at)
                .execution_options(synchronize_session=False)
            )
        )
        await detach_late_members(session, job.delivery_id, listed)
    return Delivered(channel=job.channel, latencies_s=tuple((result.at - at).total_seconds() for at in received))


async def _complete_retry(session: AsyncSession, job: DeliveryJob, result: SendFailed, now: datetime) -> Completion:
    updated = await session.scalar(
        update(Delivery)
        .where(_owned(job))
        .values(
            status=DeliveryStatus.FAILED,
            attempts=Delivery.attempts + 1,
            last_error=result.error,
            retry_at=now + retry_delay(job.attempts),
            lease_until=None,
        )
        .returning(Delivery.id)
        .execution_options(synchronize_session=False)
    )
    if updated is None:
        return _lease_lost(job)
    return RetryScheduled(channel=job.channel)


_FAILED_COLUMNS = (
    Delivery.id,
    Delivery.alert_id,
    Delivery.user_id,
    Delivery.channel,
    Delivery.received_at,
    Delivery.traceparent,
)


async def _complete_permanent(session: AsyncSession, job: DeliveryJob, result: SendFailed) -> Completion:
    row = (
        await session.execute(
            update(Delivery)
            .where(_owned(job))
            .values(
                status=DeliveryStatus.UNDELIVERABLE,
                attempts=Delivery.attempts + 1,
                last_error=result.error,
                retry_at=None,
                lease_until=None,
            )
            .returning(*_FAILED_COLUMNS)
            .execution_options(synchronize_session=False)
        )
    ).one_or_none()
    if row is None:
        return _lease_lost(job)
    failed = [row]
    if listed := _listed(job):
        # The members would fail the same way; each falls back on its own, since each belongs to its own alert.
        failed = list(
            (
                await session.execute(
                    update(Delivery)
                    .where(Delivery.id.in_(listed), Delivery.status == DeliveryStatus.PENDING)
                    .values(status=DeliveryStatus.UNDELIVERABLE, last_error=result.error, retry_at=None)
                    .returning(*_FAILED_COLUMNS)
                    .execution_options(synchronize_session=False)
                )
            ).all()
        )
        await detach_late_members(session, job.delivery_id, listed)
    fallbacks = [
        await fall_back(
            session,
            Failed(
                id=member.id,
                alert_id=member.alert_id,
                user_id=member.user_id,
                channel=member.channel,
                received_at=member.received_at,
                traceparent=member.traceparent,
            ),
        )
        for member in sorted(failed, key=lambda member: member.id)
    ]
    return GaveUp(channel=job.channel, fallbacks=tuple(fallbacks))


async def _complete_throttled(
    session: AsyncSession, job: DeliveryJob, now: datetime, throttle_refill: timedelta
) -> Completion:
    retry_at = now + throttle_refill
    updated = await session.scalar(
        update(Delivery)
        .where(_owned(job))
        .values(status=DeliveryStatus.PENDING, retry_at=retry_at, lease_until=None)
        .returning(Delivery.id)
        .execution_options(synchronize_session=False)
    )
    if updated is None:
        return _lease_lost(job)
    merged = await merge_into_digest(session, job.user_id, job.channel, now, retry_at)
    return Postponed(channel=job.channel, merged=merged)
