"""The recipient data the external channels need, loaded once per send."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.pipeline.dispatch.stage import SendFailed
from pagercutie.users.models import User

# Characters left visible when a phone number is logged.
_VISIBLE_PHONE_CHARS = 3


@dataclass(frozen=True)
class Contact:
    """How to reach an active user."""

    email: str
    phone: str | None


def mask_phone(phone: str) -> str:
    """`+420123456789` as `**********789`, so logs identify a number without disclosing it."""
    return "*" * max(len(phone) - _VISIBLE_PHONE_CHARS, 0) + phone[-_VISIBLE_PHONE_CHARS:]


async def reach(sessionmaker: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> Contact | SendFailed:
    """The user's contact data in one query; a permanent `SendFailed` when the user is gone or soft-deleted."""
    async with sessionmaker() as session:
        row = (
            await session.execute(select(User.email, User.phone, User.deleted_at).where(User.id == user_id))
        ).one_or_none()
    if row is None:
        return SendFailed("User not found", permanent=True)
    if row.deleted_at is not None:
        return SendFailed("User is deleted", permanent=True)
    return Contact(email=row.email, phone=row.phone)


async def phone_of(sessionmaker: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> str | SendFailed:
    """The phone number for the simulated channels (DEL-4); permanent `SendFailed` when there is none."""
    contact = await reach(sessionmaker, user_id)
    if isinstance(contact, SendFailed):
        return contact
    if contact.phone is None:
        return SendFailed("User has no phone number", permanent=True)
    return contact.phone
