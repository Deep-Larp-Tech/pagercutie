"""Entrypoints of the routing stage."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.errors import NotImplementedYet
from pagercutie.pipeline.messages import Opened, Renotified


async def route(session: AsyncSession, outcome: Opened | Renotified) -> list[uuid.UUID]:
    """Insert one `pending` delivery per resolved recipient and channel; returns their IDs.

    Recipients come from `rule.routing` (users, teams, on-call, DEL-3), channels from `rule.routing.channels` or
    each user's preferences for the alert's severity (DEL-2). Delivery IDs are deterministic from the alert,
    recipient, channel and notification sequence, so a repeated call inserts nothing new (SPEC §5.4).
    """
    raise NotImplementedYet("Routing")
