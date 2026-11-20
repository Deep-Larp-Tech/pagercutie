"""Users and per-user channel preferences.

Permissions follow DOMAIN.md §4: admins create, delete and re-role users; a user edits their own profile and
preferences, an admin anyone's. Persistence is not wired yet: every `_db_*` helper is a placeholder that raises
`NotImplementedYet`, so the routes keep answering 501 until `models.py` and a migration exist.
"""

import uuid
from typing import assert_never

from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth.deps import CurrentUser
from pagercutie.core.errors import Forbidden, NotFound, NotImplementedYet
from pagercutie.core.schemas import Pagination
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.users.schemas import GlobalRole, UserCreate, UserRead, UserUpdate

_USER = "User"


class UserMissing:
    """Marker returned by persistence when the user row does not exist (distinct from `None` = no preferences)."""


# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_users(session: AsyncSession, pagination: Pagination) -> list[UserRead]:
    """Any authenticated user: routing UIs need to pick user recipients."""
    return await _db_list_users(session, limit=pagination.limit, offset=pagination.offset)


async def create_user(session: AsyncSession, actor: CurrentUser, data: UserCreate) -> UserRead:
    """Admin only. Email is the login key (ADR-0024) and must be unique (see TODO)."""
    _require_admin(actor)
    email = _normalize_email(data.email)
    # TODO: a duplicate email violates the unique index on users.email; catch that and raise Conflict with a proper
    # message (409).
    return await _db_insert_user(session, data.model_copy(update={"email": email}))


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> UserRead:
    """Any authenticated user."""
    user = await _db_get_user(session, user_id)
    if user is None:
        raise NotFound(_USER, user_id)
    return user


async def update_user(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, data: UserUpdate) -> UserRead:
    """The user themselves, or an admin. Only admins may change `role`."""
    _require_self_or_admin(actor, user_id)
    if data.role is not None and actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Only admins can change a user's role")
    user = await _db_update_user(session, user_id, data)
    if user is None:
        raise NotFound(_USER, user_id)
    return user


async def delete_user(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID) -> None:
    """Admin only."""
    _require_admin(actor)
    if not await _db_delete_user(session, user_id):
        raise NotFound(_USER, user_id)


async def get_channel_preferences(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID) -> ChannelPreferences:
    """The user themselves, or an admin. No stored preferences → empty rules, i.e. UI only (DEL-2, ADR-0027)."""
    _require_self_or_admin(actor, user_id)
    match await _db_get_channel_preferences(session, user_id):
        case UserMissing():
            raise NotFound(_USER, user_id)
        case None:
            return ChannelPreferences()
        case ChannelPreferences() as prefs:
            return prefs
        case unreachable:
            assert_never(unreachable)


async def set_channel_preferences(
    session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, data: ChannelPreferences
) -> ChannelPreferences:
    """The user themselves, or an admin. PUT replaces the whole value object."""
    _require_self_or_admin(actor, user_id)
    prefs = await _db_upsert_channel_preferences(session, user_id, data)
    if prefs is None:
        raise NotFound(_USER, user_id)
    return prefs


# --- Rules -----------------------------------------------------------------------------------------------------


def _require_admin(actor: CurrentUser) -> None:
    if actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Admin only")


def _require_self_or_admin(actor: CurrentUser, user_id: uuid.UUID) -> None:
    # Checked before any DB access so non-admins can't probe which user IDs exist.
    if actor.id != user_id and actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Only the user themselves or an admin can do this")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


# --- Persistence placeholders ----------------------------------------------------------------------------------
# TODO(db): replace with queries against `users.models` once it exists (and add that module to ruff `banned-api`).
# These return DTOs for now; once models exist they should return ORM rows and the use cases validate them into
# `UserRead` (ReadModel has from_attributes=True).


async def _db_list_users(session: AsyncSession, *, limit: int, offset: int) -> list[UserRead]:
    # SELECT * FROM users ORDER BY id LIMIT :limit OFFSET :offset  (UUIDv7 → creation order)
    raise NotImplementedYet("Users")


async def _db_get_user(session: AsyncSession, user_id: uuid.UUID) -> UserRead | None:
    # SELECT * FROM users WHERE id = :user_id
    raise NotImplementedYet("Users")


async def _db_insert_user(session: AsyncSession, data: UserCreate) -> UserRead:
    # INSERT INTO users (id, email, display_name, phone, timezone, role, created_at) VALUES (uuid7(), ...)
    # The unique index on `email` raises IntegrityError on a duplicate.
    raise NotImplementedYet("Users")


async def _db_update_user(session: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> UserRead | None:
    # Omitted or null fields stay unchanged (UserUpdate docstring): apply data.model_dump(exclude_none=True).
    # UPDATE users SET <those fields>, updated_at = now() WHERE id = :user_id RETURNING *
    # No row → None (the use case turns it into 404).
    raise NotImplementedYet("Users")


async def _db_delete_user(session: AsyncSession, user_id: uuid.UUID) -> bool:
    # TODO: decide soft vs hard delete, and what happens to the user's memberships, rotation slots, personal rules
    # and channel preferences.
    # Returns False when no such user exists.
    raise NotImplementedYet("Users")


async def _db_get_channel_preferences(
    session: AsyncSession, user_id: uuid.UUID
) -> ChannelPreferences | UserMissing | None:
    # SELECT u.id, p.rules FROM users u
    #   LEFT JOIN user_channel_preferences p ON p.user_id = u.id
    #   WHERE u.id = :user_id
    # No row → UserMissing(); a row with NULL rules → None (user exists, nothing stored).
    raise NotImplementedYet("Channel preferences")


async def _db_upsert_channel_preferences(
    session: AsyncSession, user_id: uuid.UUID, data: ChannelPreferences
) -> ChannelPreferences | None:
    # INSERT ... ON CONFLICT (user_id) DO UPDATE SET rules = EXCLUDED.rules RETURNING rules
    # A foreign key violation on user_id (IntegrityError) → None (user does not exist).
    raise NotImplementedYet("Channel preferences")
