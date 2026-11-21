"""Entrypoints of the routing stage."""

import uuid
from typing import assert_never

from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.enums import Channel
from pagercutie.pipeline import recipients
from pagercutie.pipeline.messages import Opened, Renotified


async def route(session: AsyncSession, outcome: Opened | Renotified) -> list[uuid.UUID]:
    """Insert one `pending` delivery per resolved recipient and channel; returns the IDs actually inserted.

    Recipients come from `rule.routing` (users, teams, on-call, DEL-3), channels from `rule.routing.channels` or
    each recipient's preferences for the alert's severity (DEL-2): the user's own for a `user` recipient, the team's
    for `team` and `on_call`. The UI channel is always added. Windows and the rotation are evaluated at the event's
    `received_at`, the windows in the user's time zone. Soft-deleted users, teams without a rotation and rotations
    without members are skipped with a `routing.skipped` warning naming the alert and event, so an alert never fails on
    its recipients.

    A user reached through several recipients gets one delivery per channel. Delivery IDs are deterministic from the
    alert, recipient, channel and notification sequence, so a repeated call inserts nothing new (SPEC §5.4). Sends
    `NOTIFY deliveries_pending` in the caller's transaction when anything was inserted.
    """
    rule = outcome.match.rule
    event = outcome.match.event
    now = event.received_at
    log_context = {"alert_id": str(outcome.alert_id), "event_id": str(event.event_id)}
    reached = await recipients.resolve(session, rule.routing.recipients, now, log_context)
    channels = recipients.channels_by_user(reached, outcome.severity, now, rule.routing.channels)

    match outcome:
        case Opened():
            seq = 1
        case Renotified():
            seq = outcome.notification_seq
        case _:
            assert_never(outcome)

    def key(user_id: uuid.UUID, channel: Channel) -> str:
        return f"{outcome.alert_id}:{user_id}:{channel}:{seq}"

    deliveries = recipients.new_deliveries(channels, outcome.title, outcome.body, key)
    return await recipients.insert_deliveries(session, outcome.alert_id, deliveries, now)
