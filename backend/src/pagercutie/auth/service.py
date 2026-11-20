"""Login sessions (`pc_session` cookie, ADR-0024)."""

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth.models import UserSession


async def revoke_user_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Deletes every login session of the user, so each of their cookies stops working."""
    await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
