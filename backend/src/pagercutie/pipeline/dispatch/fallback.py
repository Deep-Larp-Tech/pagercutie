"""Fallback after a permanent delivery failure: the recipient's next untried channel takes over (DEL-5, ADR-0113)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, Delivery
from pagercutie.alerts.schemas import DeliveryStatus
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.enums import Channel
from pagercutie.core.templates import render_message
from pagercutie.preferences.resolution import fallback_channels
from pagercutie.users.models import User

log = structlog.get_logger("dispatch")

# Fixed forever: a fallback's ID derives from the failed delivery's, so a repeated completion inserts nothing new.
FALLBACK_NAMESPACE = uuid.UUID("0b6f1f53-3c1e-4c86-9d0e-6a3f2f7d9a41")


@dataclass(frozen=True)
class Failed:
    """A delivery that failed permanently, as the fallback needs it."""

    id: uuid.UUID
    alert_id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    # The event's ingest time; it identifies the notification round and carries over to the fallback.
    received_at: datetime
    traceparent: str | None


@dataclass(frozen=True)
class FellBack:
    """A `pending` delivery on the next channel replaces the failed one."""

    delivery_id: uuid.UUID
    from_channel: Channel
    to_channel: Channel


@dataclass(frozen=True)
class Unreachable:
    """Every channel the recipient could be reached on failed or does not exist for this notification round."""

    alert_id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    tried: tuple[Channel, ...]


type FallbackOutcome = FellBack | Unreachable


def fallback_id(failed_id: uuid.UUID, channel: Channel) -> uuid.UUID:
    """The ID of the delivery that falls back from `failed_id` to `channel`."""
    return uuid.uuid5(FALLBACK_NAMESPACE, f"{failed_id}:{channel}")


async def fall_back(session: AsyncSession, failed: Failed) -> FallbackOutcome:
    """Insert a `pending` delivery on the recipient's next channel not tried in this notification round.

    The order comes from `fallback_channels`. A channel counts as tried when the alert has a delivery to the user on
    it with the failed delivery's `received_at`, which every delivery of one notification round shares. A deleted or
    missing user is unreachable. Runs in the completion's transaction, which sends `NOTIFY deliveries_pending`.
    """
    row = (
        await session.execute(
            select(Alert.severity, Alert.title, Alert.body, User.channel_preferences, User.deleted_at)
            .join(User, User.id == failed.user_id)
            .where(Alert.id == failed.alert_id)
        )
    ).one_or_none()
    tried = frozenset(
        await session.scalars(
            select(Delivery.channel).where(
                Delivery.alert_id == failed.alert_id,
                Delivery.user_id == failed.user_id,
                Delivery.received_at == failed.received_at,
            )
        )
    ) | {failed.channel}
    if row is None or row.deleted_at is not None:
        return _unreachable(failed, tried)
    remaining = [
        channel for channel in fallback_channels(row.channel_preferences, row.severity) if channel not in tried
    ]
    if not remaining:
        return _unreachable(failed, tried)
    channel = remaining[0]
    delivery_id = fallback_id(failed.id, channel)
    await session.execute(
        insert(Delivery)
        .values(
            id=delivery_id,
            alert_id=failed.alert_id,
            user_id=failed.user_id,
            channel=channel,
            status=DeliveryStatus.PENDING,
            attempts=0,
            message=render_message(channel, row.title, row.body),
            received_at=failed.received_at,
            traceparent=failed.traceparent,
        )
        .on_conflict_do_nothing(index_elements=[Delivery.id])
    )
    await notify(session, NotifyChannel.DELIVERIES_PENDING)
    log.info(
        "dispatch.fell_back",
        message="Delivery failed permanently, trying the next channel",
        delivery_id=str(failed.id),
        fallback_id=str(delivery_id),
        from_channel=failed.channel,
        to_channel=channel,
    )
    return FellBack(delivery_id=delivery_id, from_channel=failed.channel, to_channel=channel)


def _unreachable(failed: Failed, tried: frozenset[Channel]) -> Unreachable:
    ordered = tuple(channel for channel in Channel if channel in tried)
    log.warning(
        "dispatch.unreachable",
        message="Recipient could not be reached on any channel",
        alert_id=str(failed.alert_id),
        user_id=str(failed.user_id),
        tried=[str(channel) for channel in ordered],
    )
    return Unreachable(alert_id=failed.alert_id, user_id=failed.user_id, channel=failed.channel, tried=ordered)
