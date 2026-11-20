"""Users and per-user channel preferences.

Permissions follow DOMAIN.md §4: admins create, delete and re-role users; a user edits their own profile and
preferences, an admin anyone's. Deleting a user is a soft delete (`deleted_at`): every read and update here ignores
soft-deleted users. Channel preferences answer 501 until their models change.
"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth import service as auth_service
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.errors import Forbidden, NotFound, NotImplementedYet
from pagercutie.core.schemas import Pagination
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole, UserCreate, UserRead, UserUpdate

_USER = "User"


# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_users(session: AsyncSession, pagination: Pagination) -> list[UserRead]:
    """Any authenticated user: routing UIs need to pick user recipients."""
    users = await _db_list_users(session, limit=pagination.limit, offset=pagination.offset)
    return [UserRead.model_validate(user) for user in users]


async def create_user(session: AsyncSession, actor: CurrentUser, data: UserCreate) -> UserRead:
    """Admin only. Email is the login key (ADR-0024) and must be unique among active users (see TODO)."""
    _require_admin(actor)
    email = _normalize_email(data.email)
    # TODO: a duplicate email violates the partial unique index ix_users_email (active users only); catch that and
    # raise Conflict with a proper message (409).
    return UserRead.model_validate(await _db_insert_user(session, data.model_copy(update={"email": email})))


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> UserRead:
    """Any authenticated user."""
    user = await _db_get_user(session, user_id)
    if user is None:
        raise NotFound(_USER, user_id)
    return UserRead.model_validate(user)


async def update_user(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, data: UserUpdate) -> UserRead:
    """The user themselves, or an admin. Only admins may change `role`."""
    _require_self_or_admin(actor, user_id)
    if data.role is not None and actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Only admins can change a user's role")
    user = await _db_update_user(session, user_id, data)
    if user is None:
        raise NotFound(_USER, user_id)
    return UserRead.model_validate(user)


async def delete_user(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID) -> None:
    """Admin only. Soft delete: logs the user out everywhere; team memberships and rotation slots stay."""
    _require_admin(actor)
    if not await _db_soft_delete_user(session, user_id):
        raise NotFound(_USER, user_id)
    await auth_service.revoke_user_sessions(session, user_id)


async def get_channel_preferences(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID) -> ChannelPreferences:
    """The user themselves, or an admin. A new user has empty rules, i.e. UI only (DEL-2, ADR-0027)."""
    _require_self_or_admin(actor, user_id)
    raise NotImplementedYet("Channel preferences")


async def set_channel_preferences(
    session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, data: ChannelPreferences
) -> ChannelPreferences:
    """The user themselves, or an admin. PUT replaces the whole value object."""
    _require_self_or_admin(actor, user_id)
    raise NotImplementedYet("Channel preferences")


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


# --- Persistence -----------------------------------------------------------------------------------------------
# Soft-deleted users are filtered out here; a missing user comes back as `None` and the use cases turn it into 404.

_ACTIVE = User.deleted_at.is_(None)


async def _db_list_users(session: AsyncSession, *, limit: int, offset: int) -> list[User]:
    # UUIDv7 ids sort in creation order.
    users = await session.scalars(select(User).where(_ACTIVE).order_by(User.id).limit(limit).offset(offset))
    return list(users)


async def _db_get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.scalar(select(User).where(User.id == user_id, _ACTIVE))


async def _db_insert_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(**data.model_dump())
    session.add(user)
    # Sends the INSERT now so a duplicate email fails here; `created_at` comes back with RETURNING.
    await session.flush()
    return user


async def _db_update_user(session: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> User | None:
    # Omitted or null fields stay unchanged (UserUpdate docstring).
    changes = data.model_dump(exclude_none=True)
    if not changes:
        return await _db_get_user(session, user_id)
    return await session.scalar(update(User).where(User.id == user_id, _ACTIVE).values(**changes).returning(User))


async def _db_soft_delete_user(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """False when no active user has this id, so deleting twice is a 404."""
    deleted_id = await session.scalar(
        update(User).where(User.id == user_id, _ACTIVE).values(deleted_at=func.now()).returning(User.id)
    )
    return deleted_id is not None
