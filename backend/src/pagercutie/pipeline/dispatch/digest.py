"""Digest policy of the dispatch stage: throttled deliveries merge into one digest delivery row (SPEC §9, ADR-0081)."""

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import Select, and_, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pagercutie.alerts.models import Delivery
from pagercutie.alerts.schemas import DeliveryStatus
from pagercutie.core.enums import Channel

log = structlog.get_logger("dispatch")

# Messages listed in a digest; the rest are only counted, so an SMS digest stays short.
DIGEST_MAX_LINES = 10
DIGEST_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "digest.pagercutie")


@dataclass(frozen=True)
class Member:
    """A `pending` delivery carried by a digest."""

    id: uuid.UUID
    alert_id: uuid.UUID
    message: str
    created_at: datetime
    received_at: datetime


@dataclass(frozen=True)
class Merged:
    """Throttled deliveries joined a digest."""

    digest_id: uuid.UUID
    # True when this merge inserted the digest row; False when the deliveries joined an open one.
    created: bool
    # Deliveries that joined in this merge.
    joined: int


def digest_message(messages: Sequence[str]) -> str:
    """One line per message (its first line), at most `DIGEST_MAX_LINES`, then a count of the rest."""
    lines = [message.strip().split("\n", 1)[0] for message in messages[:DIGEST_MAX_LINES]]
    text = "\n".join([f"{len(messages)} notifications held back by the rate limit:", *(f"- {line}" for line in lines)])
    if len(messages) > DIGEST_MAX_LINES:
        text += f"\n... and {len(messages) - DIGEST_MAX_LINES} more"
    return text


def _ordered(rows: Sequence[Member]) -> list[Member]:
    # Ordered like the message lines; the oldest member's alert is the one the digest is listed under.
    return sorted(rows, key=lambda row: (row.created_at, row.id))


def _select_members() -> Select[uuid.UUID, uuid.UUID, str, datetime, datetime]:
    """The columns of a `Member`, in its field order."""
    return select(Delivery.id, Delivery.alert_id, Delivery.message, Delivery.created_at, Delivery.received_at)


@dataclass(frozen=True)
class Digests:
    """The digests among a set of claimed deliveries and their `pending` members."""

    # Every claimed delivery that has ever carried a member.
    ids: frozenset[uuid.UUID]
    # `pending` members of each digest, ordered like the message lines.
    pending: dict[uuid.UUID, list[Member]]


async def load_digests(session: AsyncSession, delivery_ids: Collection[uuid.UUID]) -> Digests:
    """Which of `delivery_ids` are digests, and the members each one carries now."""
    if not delivery_ids:
        return Digests(ids=frozenset(), pending={})
    rows = (
        await session.execute(
            select(Delivery.digest_id, Delivery.status)
            .add_columns(Delivery.id, Delivery.alert_id, Delivery.message, Delivery.created_at, Delivery.received_at)
            .where(Delivery.digest_id.in_(delivery_ids))
        )
    ).all()
    ids: set[uuid.UUID] = set()
    pending: dict[uuid.UUID, list[Member]] = {}
    for digest_id, status, member_id, alert_id, message, created_at, received_at in rows:
        if digest_id is None:
            continue
        ids.add(digest_id)
        if status is DeliveryStatus.PENDING:
            pending.setdefault(digest_id, []).append(Member(member_id, alert_id, message, created_at, received_at))
    return Digests(ids=frozenset(ids), pending={digest_id: _ordered(members) for digest_id, members in pending.items()})


async def detach_late_members(session: AsyncSession, digest_id: uuid.UUID, listed: Collection[uuid.UUID]) -> None:
    """Release `pending` members that joined after the digest's message was composed, so they are sent on their own.

    A member joins a digest only while no dispatcher holds it; one whose lease expired mid-send can gain members the
    sent message did not list (ADR-0113).
    """
    await session.execute(
        update(Delivery)
        .where(
            Delivery.digest_id == digest_id,
            Delivery.status == DeliveryStatus.PENDING,
            Delivery.id.not_in(listed),
        )
        .values(digest_id=None)
        .execution_options(synchronize_session=False)
    )


async def merge_into_digest(
    session: AsyncSession, user_id: uuid.UUID, channel: Channel, now: datetime, retry_at: datetime
) -> Merged | None:
    """Fold the undelivered `pending` deliveries of one recipient and channel into one digest delivery (SPEC §9).

    Candidates are `pending`, not leased by a dispatcher, not in a digest yet and not a digest themselves. They join
    the recipient's open digest (a `pending` digest no dispatcher has claimed since it was completed) and rewrite its
    message; without one, two candidates start a new digest due at `retry_at`. Members stay `pending` with
    `digest_id` set, which keeps `claim_due` away from them. A new digest's ID derives from its first members' IDs, so
    a repeated merge of the same set inserts one row. Merges of one recipient and channel run one at a time, so a
    burst of throttled deliveries ends in one digest. Returns None when nothing merged.
    """
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"digest:{user_id}:{channel}", 0))))
    member = aliased(Delivery)
    mine = and_(
        Delivery.user_id == user_id,
        Delivery.channel == channel,
        Delivery.status == DeliveryStatus.PENDING,
        Delivery.digest_id.is_(None),
    )
    # Locks rows that another replica's claim holds are skipped; they join a digest on a later throttle.
    candidates = [
        Member(*row)
        for row in (
            await session.execute(
                _select_members()
                .where(
                    mine,
                    (Delivery.lease_until.is_(None)) | (Delivery.lease_until < now),
                    ~exists().where(member.digest_id == Delivery.id),
                )
                .with_for_update(skip_locked=True, of=Delivery)
            )
        ).all()
    ]
    if not candidates:
        return None
    # A digest a dispatcher still holds, or held until its lease expired, may be mid-send: never extend it.
    digest_id = await session.scalar(
        select(Delivery.id)
        .where(mine, Delivery.lease_until.is_(None), exists().where(member.digest_id == Delivery.id))
        .order_by(Delivery.created_at, Delivery.id)
        .limit(1)
        .with_for_update(skip_locked=True, of=Delivery)
    )
    created = digest_id is None
    if digest_id is None:
        if len(candidates) < 2:
            return None
        digest_id = uuid.uuid5(DIGEST_NAMESPACE, ",".join(sorted(str(candidate.id) for candidate in candidates)))
        members = _ordered(candidates)
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
        held = [
            Member(*row)
            for row in (
                await session.execute(
                    _select_members().where(Delivery.digest_id == digest_id, Delivery.status == DeliveryStatus.PENDING)
                )
            ).all()
        ]
        members = _ordered([*held, *candidates])
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
    return Merged(digest_id=digest_id, created=created, joined=len(candidates))
