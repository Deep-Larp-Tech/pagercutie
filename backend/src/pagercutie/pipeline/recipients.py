"""Recipient resolution and delivery inserts, shared by the routing stage and the executor's escalation (ADR-0102).

Not a stage: it imports no stage, so both stages may import it under the import-linter contracts (SPEC §5.5).
"""

import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
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
from pagercutie.core.enums import Channel, Severity
from pagercutie.core.templates import render_message
from pagercutie.preferences.resolution import resolve_channels
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.rules.schemas import OnCallRecipient, Recipient, TeamRecipient, UserRecipient
from pagercutie.teams.models import Membership, Rotation, Team
from pagercutie.teams.rotation import on_call_at
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User

# Fixed forever: changing it changes every delivery ID, so a retried outcome would insert duplicates (SPEC §5.4).
DELIVERY_NAMESPACE = uuid.UUID("5b0d2f4e-8f0a-4c52-9a43-0d5d3a7c1e68")

_NOTIFIED_ROLES = (TeamRole.LEAD, TeamRole.MEMBER)

_log = structlog.get_logger("routing")


@dataclass(frozen=True)
class Reached:
    """An active user a recipient entry reaches, with the preferences that choose their channels (DEL-2)."""

    user: User
    preferences: ChannelPreferences


@dataclass(frozen=True)
class NewDelivery:
    """One `pending` delivery to insert."""

    # Deterministic (`delivery_id`), so inserting the same delivery twice inserts it once (SPEC §5.4).
    id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    message: str


def delivery_id(key: str) -> uuid.UUID:
    """The delivery ID for `key`, which names the alert, user, channel and why the delivery exists."""
    return uuid.uuid5(DELIVERY_NAMESPACE, key)


async def resolve(
    session: AsyncSession, recipients: Sequence[Recipient], at: datetime, log_context: Mapping[str, str]
) -> list[Reached]:
    """The active users `recipients` reach at `at`, in recipient order, a user once per entry that reaches them.

    `user` entries use the user's own preferences, `team` (leads and members) and `on_call` the team's. Missing teams
    and users, soft-deleted users, teams without a rotation and rotations without members are skipped with a
    `routing.skipped` warning carrying `log_context` (e.g. the alert and event). Issues one query per recipient type,
    whatever the number of entries.
    """
    team_ids = {r.team_id for r in recipients if isinstance(r, TeamRecipient | OnCallRecipient)}
    teams = await _by_id(session, Team, team_ids)
    member_team_ids = [r.team_id for r in recipients if isinstance(r, TeamRecipient) and r.team_id in teams]
    members: dict[uuid.UUID, list[User]] = {}
    if member_team_ids:
        for team_id, user in await session.execute(
            select(Membership.team_id, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.team_id.in_(member_team_ids), Membership.role.in_(_NOTIFIED_ROLES))
            .order_by(User.id)
        ):
            members.setdefault(team_id, []).append(user)
    on_call_team_ids = [r.team_id for r in recipients if isinstance(r, OnCallRecipient) and r.team_id in teams]
    rotations: dict[uuid.UUID, Rotation] = {}
    if on_call_team_ids:
        rotations = {
            rotation.team_id: rotation
            for rotation in await session.scalars(
                select(Rotation).where(Rotation.team_id.in_(on_call_team_ids)).options(selectinload(Rotation.members))
            )
        }
    on_call: dict[uuid.UUID, uuid.UUID] = {}
    for team_id, rotation in rotations.items():
        shift = on_call_at(rotation, at)
        if shift is not None:
            on_call[team_id] = shift.user_id
    user_ids = {r.user_id for r in recipients if isinstance(r, UserRecipient)} | set(on_call.values())
    users = await _by_id(session, User, user_ids)

    def active(user_id: uuid.UUID) -> User | None:
        user = users.get(user_id)
        if user is None:
            _skip(log_context, "user_not_found", user_id=user_id)
            return None
        return user if _is_active(log_context, user) else None

    reached: list[Reached] = []
    for recipient in recipients:
        match recipient:
            case UserRecipient():
                user = active(recipient.user_id)
                if user is not None:
                    reached.append(Reached(user, user.channel_preferences))
            case TeamRecipient():
                team = teams.get(recipient.team_id)
                if team is None:
                    _skip(log_context, "team_not_found", team_id=recipient.team_id)
                    continue
                reached.extend(
                    Reached(user, team.channel_preferences)
                    for user in members.get(team.id, [])
                    if _is_active(log_context, user)
                )
            case OnCallRecipient():
                team = teams.get(recipient.team_id)
                if team is None:
                    _skip(log_context, "team_not_found", team_id=recipient.team_id)
                    continue
                if team.id not in rotations:
                    _skip(log_context, "no_rotation", recipient_type=recipient.type, team_id=team.id)
                    continue
                if team.id not in on_call:
                    _skip(log_context, "rotation_without_members", recipient_type=recipient.type, team_id=team.id)
                    continue
                user = active(on_call[team.id])
                if user is not None:
                    reached.append(Reached(user, team.channel_preferences))
            case _:
                assert_never(recipient)
    return reached


def channels_by_user(
    reached: Iterable[Reached], severity: Severity, at: datetime, override: Sequence[Channel] | None
) -> dict[uuid.UUID, set[Channel]]:
    """Each reached user's channels: `override` when given, else their preferences for `severity` at `at` in the
    user's time zone (DEL-2, DEL-3); the UI channel always. A user reached several times gets the union."""
    channels: dict[uuid.UUID, set[Channel]] = {}
    for entry in reached:
        chosen = (
            set(override)
            if override is not None
            else set(resolve_channels(entry.preferences, severity, at, entry.user.timezone))
        )
        chosen.add(Channel.UI)
        channels.setdefault(entry.user.id, set()).update(chosen)
    return channels


def new_deliveries(
    channels: dict[uuid.UUID, set[Channel]],
    title: str,
    body: str | None,
    key: Callable[[uuid.UUID, Channel], str],
) -> list[NewDelivery]:
    """One delivery per user and channel, in `Channel` order, with the ID `delivery_id(key(user_id, channel))`."""
    return [
        NewDelivery(
            id=delivery_id(key(user_id, channel)),
            user_id=user_id,
            channel=channel,
            message=render_message(channel, title, body),
        )
        for user_id, user_channels in channels.items()
        for channel in Channel
        if channel in user_channels
    ]


async def insert_deliveries(
    session: AsyncSession, alert_id: uuid.UUID, deliveries: Sequence[NewDelivery], received_at: datetime
) -> list[uuid.UUID]:
    """Insert `deliveries` as `pending`, skipping IDs that exist, and return the IDs inserted, in input order.

    Stores the current span's trace context, so the send span links to it (SPEC §13). Sends `NOTIFY
    deliveries_pending` in the caller's transaction when anything was inserted.
    """
    if not deliveries:
        return []
    traceparent = current_traceparent()
    result = await session.execute(
        insert(Delivery)
        .values(
            [
                {
                    "id": delivery.id,
                    "alert_id": alert_id,
                    "user_id": delivery.user_id,
                    "channel": delivery.channel,
                    "status": DeliveryStatus.PENDING,
                    "attempts": 0,
                    "message": delivery.message,
                    "received_at": received_at,
                    "traceparent": traceparent,
                }
                for delivery in deliveries
            ]
        )
        .on_conflict_do_nothing(index_elements=[Delivery.id])
        .returning(Delivery.id)
    )
    inserted = set(result.scalars())
    if inserted:
        await notify(session, NotifyChannel.DELIVERIES_PENDING)
    return [delivery.id for delivery in deliveries if delivery.id in inserted]


def current_traceparent() -> str | None:
    """W3C trace context of the current span; `None` outside a span, so a later span starts its own trace."""
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier.get("traceparent")


async def _by_id[T: (Team, User)](session: AsyncSession, model: type[T], ids: set[uuid.UUID]) -> dict[uuid.UUID, T]:
    if not ids:
        return {}
    return {row.id: row for row in await session.scalars(select(model).where(model.id.in_(ids)))}


def _is_active(log_context: Mapping[str, str], user: User) -> bool:
    if user.deleted_at is not None:
        _skip(log_context, "user_deleted", user_id=user.id)
        return False
    return True


def _skip(log_context: Mapping[str, str], reason: str, **context: object) -> None:
    _log.warning("routing.skipped", message="Recipient skipped", reason=reason, **log_context, **context)
