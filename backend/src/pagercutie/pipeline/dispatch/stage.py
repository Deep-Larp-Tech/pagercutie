"""Entrypoints of the dispatch stage, called by its loop in every replica (`worker.py`)."""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, assert_never

import structlog
from opentelemetry import metrics
from sqlalchemy import ColumnElement, and_, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pagercutie.alerts.models import Delivery
from pagercutie.alerts.schemas import DeliveryStatus
from pagercutie.core.enums import Channel

log = structlog.get_logger("dispatch")

_meter = metrics.get_meter("pagercutie.dispatch")
_deliveries = _meter.create_counter("deliveries_total", description="Deliveries that ended sent or failed, by channel")
_retries = _meter.create_counter("delivery_retries_total", description="Failed sends scheduled for another attempt")
_latency = _meter.create_histogram(
    "end_to_end_latency_seconds",
    unit="s",
    description="Time from ingest receiving the event to the delivery being sent",
    explicit_bucket_boundaries_advisory=[0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300],
)

MAX_BACKOFF_SECONDS = 300
# Messages listed in a digest; the rest are only counted, so an SMS digest stays short.
DIGEST_MAX_LINES = 10
DIGEST_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "digest.pagercutie")


@dataclass(frozen=True)
class DeliveryJob:
    """A `pending` delivery leased to this replica by `claim_due`."""

    delivery_id: uuid.UUID
    alert_id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    # Rendered for the channel when routing created the delivery.
    message: str
    # Earlier send attempts; the basis of the retry backoff.
    attempts: int
    # End of this claim's lease. `complete` only writes while the row still holds this value, so a replica whose
    # lease expired cannot overwrite the replica that claimed the row after it (SPEC §10).
    lease_until: datetime
    # W3C trace context of the ingest request; the send span links to it (SPEC §14).
    traceparent: str | None = None


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


async def claim_due(session: AsyncSession, limit: int, now: datetime, lease: timedelta) -> list[DeliveryJob]:
    """Lease up to `limit` due deliveries with `FOR UPDATE SKIP LOCKED` (SPEC §10); the caller commits.

    Due means `pending` with no `retry_at` or one that passed, or `failed` with a `retry_at` that passed, and no live
    lease. Deliveries merged into a digest wait for the digest instead.
    """
    lease_until = now + lease
    due = or_(
        and_(
            Delivery.status == DeliveryStatus.PENDING,
            or_(Delivery.retry_at.is_(None), Delivery.retry_at <= now),
        ),
        and_(Delivery.status == DeliveryStatus.FAILED, Delivery.retry_at <= now),
    )
    # MATERIALIZED: the planner must run the locking subquery once, or the UPDATE could touch more than `limit` rows.
    claimable = (
        select(Delivery.id)
        .where(due, or_(Delivery.lease_until.is_(None), Delivery.lease_until < now), Delivery.digest_id.is_(None))
        .order_by(Delivery.created_at, Delivery.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .cte("claimable")
        .prefix_with("MATERIALIZED")
    )
    claimed = await session.execute(
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
    return [
        DeliveryJob(
            delivery_id=row.id,
            alert_id=row.alert_id,
            user_id=row.user_id,
            channel=row.channel,
            message=row.message,
            attempts=row.attempts,
            lease_until=lease_until,
            traceparent=row.traceparent,
        )
        for row in sorted(claimed, key=lambda row: (row.created_at, row.id))
    ]


async def send(job: DeliveryJob, adapters: Mapping[Channel, ChannelAdapter], throttle: Throttle) -> SendResult:
    """Throttle, then send through the adapter for `job.channel`. Runs outside any transaction."""
    try:
        if is_throttled_channel(job.channel) and not await throttle.allow(job.user_id):
            return Throttled()
        return await adapters[job.channel].send(job)
    except Exception as error:
        # The Protocol asks adapters to return failures, but a bug in one must not stop the loop or the other sends.
        log.exception(
            "dispatch.send_raised",
            message="Channel adapter raised instead of returning a failure",
            delivery_id=str(job.delivery_id),
            channel=job.channel,
        )
        return SendFailed(error=f"{type(error).__name__}: {error}")


async def complete(
    session: AsyncSession, job: DeliveryJob, result: SendResult, now: datetime, throttle_refill: timedelta
) -> None:
    """Mark the delivery `sent`, or `failed` with `retry_at`, and end its lease (DEL-6).

    Writes only while the row still holds `job.lease_until`; otherwise another replica owns the delivery and this
    result is dropped. `throttle_refill` is the time until the recipient's bucket holds a token again.
    """
    match result:
        case Sent():
            await _complete_sent(session, job, result)
        case SendFailed():
            await _complete_failed(session, job, result, now)
        case Throttled():
            await _complete_throttled(session, job, now, throttle_refill)
        case _:
            assert_never(result)


def _owned(job: DeliveryJob) -> ColumnElement[bool]:
    return and_(Delivery.id == job.delivery_id, Delivery.lease_until == job.lease_until)


def _lease_lost(job: DeliveryJob) -> None:
    log.warning(
        "dispatch.lease_lost",
        message="Delivery lease expired and another replica took over; dropping this result",
        delivery_id=str(job.delivery_id),
    )


async def _complete_sent(session: AsyncSession, job: DeliveryJob, result: Sent) -> None:
    row = (
        await session.execute(
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
    ).one_or_none()
    if row is None:
        _lease_lost(job)
        return
    # A digest carries its members: each waited since its own event, not since the digest row was created.
    members = await session.execute(
        update(Delivery)
        .where(Delivery.digest_id == job.delivery_id, Delivery.status == DeliveryStatus.PENDING)
        .values(status=DeliveryStatus.SENT, sent_at=result.at, last_error=None)
        .returning(Delivery.received_at)
        .execution_options(synchronize_session=False)
    )
    received = [member.received_at for member in members] or [row.received_at]
    _deliveries.add(1, {"channel": job.channel.value, "status": DeliveryStatus.SENT.value})
    for received_at in received:
        _latency.record((result.at - received_at).total_seconds(), {"channel": job.channel.value})


async def _complete_failed(session: AsyncSession, job: DeliveryJob, result: SendFailed, now: datetime) -> None:
    retry_at = None if result.permanent else now + retry_delay(job.attempts)
    row = (
        await session.execute(
            update(Delivery)
            .where(_owned(job))
            .values(
                status=DeliveryStatus.FAILED,
                attempts=Delivery.attempts + 1,
                last_error=result.error,
                retry_at=retry_at,
                lease_until=None,
            )
            .returning(Delivery.id)
            .execution_options(synchronize_session=False)
        )
    ).one_or_none()
    if row is None:
        _lease_lost(job)
        return
    if result.permanent:
        # Members of a digest that can never be sent would stay `pending` for good; they would fail the same way.
        await session.execute(
            update(Delivery)
            .where(Delivery.digest_id == job.delivery_id, Delivery.status == DeliveryStatus.PENDING)
            .values(status=DeliveryStatus.FAILED, last_error=result.error, retry_at=None)
            .execution_options(synchronize_session=False)
        )
    else:
        _retries.add(1, {"channel": job.channel.value})
    _deliveries.add(1, {"channel": job.channel.value, "status": DeliveryStatus.FAILED.value})


async def _complete_throttled(
    session: AsyncSession, job: DeliveryJob, now: datetime, throttle_refill: timedelta
) -> None:
    retry_at = now + throttle_refill
    row = (
        await session.execute(
            update(Delivery)
            .where(_owned(job))
            .values(status=DeliveryStatus.PENDING, retry_at=retry_at, lease_until=None)
            .returning(Delivery.id)
            .execution_options(synchronize_session=False)
        )
    ).one_or_none()
    if row is None:
        _lease_lost(job)
        return
    await merge_into_digest(session, job.user_id, job.channel, now, retry_at)


def digest_message(messages: Sequence[str]) -> str:
    """One line per message (its first line), at most `DIGEST_MAX_LINES`, then a count of the rest."""
    lines = [message.strip().split("\n", 1)[0] for message in messages[:DIGEST_MAX_LINES]]
    text = "\n".join([f"{len(messages)} notifications held back by the rate limit:", *(f"- {line}" for line in lines)])
    if len(messages) > DIGEST_MAX_LINES:
        text += f"\n... and {len(messages) - DIGEST_MAX_LINES} more"
    return text


async def merge_into_digest(
    session: AsyncSession, user_id: uuid.UUID, channel: Channel, now: datetime, retry_at: datetime
) -> uuid.UUID | None:
    """Fold the undelivered `pending` deliveries of one recipient and channel into one digest delivery (SPEC §9).

    Candidates are `pending`, not leased by a dispatcher, not in a digest yet and not a digest themselves. They join
    the recipient's open digest (a `pending` digest no dispatcher holds) and rewrite its message; without one, two
    candidates start a new digest due at `retry_at`. Members stay `pending` with `digest_id` set, which keeps
    `claim_due` away from them, and are marked `sent` when the digest is. A new digest's ID derives from its first
    members' IDs, so a repeated merge of the same set inserts one row. Merges of one recipient and channel run one at
    a time, so a burst of throttled deliveries ends in one digest. Returns the digest ID, or None when nothing merged.
    """
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"digest:{user_id}:{channel}", 0))))
    member = aliased(Delivery)
    unleased = or_(Delivery.lease_until.is_(None), Delivery.lease_until < now)
    mine = and_(
        Delivery.user_id == user_id,
        Delivery.channel == channel,
        Delivery.status == DeliveryStatus.PENDING,
        unleased,
    )
    # Locks rows that another replica's claim holds are skipped; they join a digest on a later throttle.
    candidates = (
        await session.execute(
            select(Delivery.id, Delivery.alert_id, Delivery.message, Delivery.created_at, Delivery.received_at)
            .where(mine, Delivery.digest_id.is_(None), ~exists().where(member.digest_id == Delivery.id))
            .with_for_update(skip_locked=True, of=Delivery)
        )
    ).all()
    if not candidates:
        return None
    digest_id = await session.scalar(
        select(Delivery.id)
        .where(mine, Delivery.digest_id.is_(None), exists().where(member.digest_id == Delivery.id))
        .order_by(Delivery.created_at, Delivery.id)
        .limit(1)
        .with_for_update(skip_locked=True, of=Delivery)
    )
    if digest_id is None:
        if len(candidates) < 2:
            return None
        digest_id = uuid.uuid5(DIGEST_NAMESPACE, ",".join(sorted(str(candidate.id) for candidate in candidates)))
        # Ordered like the message lines; the oldest member's alert is the one the digest is listed under.
        members = sorted(candidates, key=lambda row: (row.created_at, row.id))
        await session.execute(
            insert(Delivery)
            .values(
                id=digest_id,
                alert_id=members[0].alert_id,
                user_id=user_id,
                channel=channel,
                status=DeliveryStatus.PENDING,
                attempts=0,
                message=digest_message([row.message for row in members]),
                received_at=min(row.received_at for row in members),
                retry_at=retry_at,
            )
            .on_conflict_do_nothing(index_elements=[Delivery.id])
        )
    else:
        held = (
            await session.execute(
                select(
                    Delivery.id, Delivery.alert_id, Delivery.message, Delivery.created_at, Delivery.received_at
                ).where(Delivery.digest_id == digest_id, Delivery.status == DeliveryStatus.PENDING)
            )
        ).all()
        members = sorted([*held, *candidates], key=lambda row: (row.created_at, row.id))
        await session.execute(
            update(Delivery)
            .where(Delivery.id == digest_id)
            .values(message=digest_message([row.message for row in members]))
            .execution_options(synchronize_session=False)
        )
    await session.execute(
        update(Delivery)
        .where(Delivery.id.in_([candidate.id for candidate in candidates]))
        .values(digest_id=digest_id)
        .execution_options(synchronize_session=False)
    )
    log.info(
        "dispatch.digested",
        message="Merged throttled deliveries into a digest",
        digest_id=str(digest_id),
        user_id=str(user_id),
        channel=channel,
        members=len(members),
    )
    return digest_id
