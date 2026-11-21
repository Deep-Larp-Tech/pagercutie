"""Entrypoints of the routing stage."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

import structlog
from opentelemetry.propagate import inject
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pagercutie.alerts.models import Delivery
from pagercutie.alerts.schemas import DeliveryStatus
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.enums import Channel
from pagercutie.core.templates import render_message
from pagercutie.pipeline.messages import Opened, Renotified
from pagercutie.preferences.resolution import resolve_channels
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.rules.schemas import OnCallRecipient, Recipient, TeamRecipient, UserRecipient
from pagercutie.teams.models import Membership, Rotation, Team
from pagercutie.teams.rotation import on_call_at
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User

log = structlog.get_logger("routing")

# Fixed forever: changing it changes every delivery ID, so a retried outcome would insert duplicates (SPEC §5.4).
DELIVERY_NAMESPACE = uuid.UUID("5b0d2f4e-8f0a-4c52-9a43-0d5d3a7c1e68")

_NOTIFIED_ROLES = (TeamRole.LEAD, TeamRole.MEMBER)


@dataclass(frozen=True)
class _Row:
    """One delivery to insert."""

    id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    message: str


async def route(session: AsyncSession, outcome: Opened | Renotified) -> list[uuid.UUID]:
    """Insert one `pending` delivery per resolved recipient and channel; returns the IDs actually inserted.

    Recipients come from `rule.routing` (users, teams, on-call, DEL-3), channels from `rule.routing.channels` or
    each recipient's preferences for the alert's severity (DEL-2): the user's own for a `user` recipient, the team's
    for `team` and `on_call`. The UI channel is always added. Windows and the rotation are evaluated at the event's
    `received_at`, the windows in the user's time zone. Soft-deleted users, teams without a rotation and rotations
    without members are skipped with a `routing.skipped` warning, so an alert never fails on its recipients.

    A user reached through several recipients gets one delivery per channel. Delivery IDs are deterministic from the
    alert, recipient, channel and notification sequence, so a repeated call inserts nothing new (SPEC §5.4). Sends
    `NOTIFY deliveries_pending` in the caller's transaction when anything was inserted.
    """
    alert_id, content = outcome.alert_id, outcome.content
    rule = outcome.match.rule
    now = outcome.match.event.received_at

    channels_by_user: dict[uuid.UUID, set[Channel]] = {}
    for recipient in rule.routing.recipients:
        for user, preferences in await _resolve(session, recipient, now):
            channels = (
                set(rule.routing.channels)
                if rule.routing.channels is not None
                else set(resolve_channels(preferences, content.severity, now, user.timezone))
            )
            channels.add(Channel.UI)
            channels_by_user.setdefault(user.id, set()).update(channels)

    match outcome:
        case Opened():
            seq = 1
        case Renotified():
            seq = outcome.notification_seq
        case _:
            assert_never(outcome)

    rows = [
        _Row(
            id=uuid.uuid5(DELIVERY_NAMESPACE, f"{alert_id}:{user_id}:{channel}:{seq}"),
            user_id=user_id,
            channel=channel,
            message=render_message(channel, content.title, content.body),
        )
        for user_id, channels in channels_by_user.items()
        for channel in Channel
        if channel in channels
    ]
    if not rows:
        return []

    traceparent = _traceparent()
    result = await session.execute(
        insert(Delivery)
        .values(
            [
                {
                    "id": row.id,
                    "alert_id": alert_id,
                    "user_id": row.user_id,
                    "channel": row.channel,
                    "status": DeliveryStatus.PENDING,
                    "attempts": 0,
                    "message": row.message,
                    "received_at": now,
                    "traceparent": traceparent,
                }
                for row in rows
            ]
        )
        .on_conflict_do_nothing(index_elements=[Delivery.id])
        .returning(Delivery.id)
    )
    inserted = set(result.scalars())
    if inserted:
        await notify(session, NotifyChannel.DELIVERIES_PENDING)
    return [row.id for row in rows if row.id in inserted]


async def _resolve(session: AsyncSession, recipient: Recipient, now: datetime) -> list[tuple[User, ChannelPreferences]]:
    """The active users a recipient entry reaches, each with the preferences that choose their channels."""
    match recipient:
        case UserRecipient():
            user = await _active_user(session, recipient.user_id)
            return [] if user is None else [(user, user.channel_preferences)]
        case TeamRecipient():
            team = await _team(session, recipient.team_id)
            if team is None:
                return []
            users = await session.scalars(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(Membership.team_id == team.id, Membership.role.in_(_NOTIFIED_ROLES))
                .order_by(User.id)
            )
            return [(user, team.channel_preferences) for user in users if _is_active(user)]
        case OnCallRecipient():
            team = await _team(session, recipient.team_id)
            if team is None:
                return []
            rotation = await session.scalar(
                select(Rotation).where(Rotation.team_id == team.id).options(selectinload(Rotation.members))
            )
            if rotation is None:
                _skip("no_rotation", recipient_type=recipient.type, team_id=team.id)
                return []
            on_call = on_call_at(rotation, now)
            if on_call is None:
                _skip("rotation_without_members", recipient_type=recipient.type, team_id=team.id)
                return []
            user = await _active_user(session, on_call.user_id)
            return [] if user is None else [(user, team.channel_preferences)]
        case _:
            assert_never(recipient)


async def _team(session: AsyncSession, team_id: uuid.UUID) -> Team | None:
    team = await session.scalar(select(Team).where(Team.id == team_id))
    if team is None:
        _skip("team_not_found", team_id=team_id)
    return team


async def _active_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        _skip("user_not_found", user_id=user_id)
        return None
    return user if _is_active(user) else None


def _is_active(user: User) -> bool:
    if user.deleted_at is not None:
        _skip("user_deleted", user_id=user.id)
        return False
    return True


def _skip(reason: str, **context: object) -> None:
    log.warning("routing.skipped", message="Recipient skipped", reason=reason, **context)


def _traceparent() -> str | None:
    """W3C trace context of the current span; `None` outside a span, so the send span starts its own trace."""
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier.get("traceparent")
