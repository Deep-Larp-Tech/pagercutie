"""Users and per-user channel preferences.

Permissions follow DOMAIN.md §4: admins create, delete and re-role users; a user edits their own profile and
preferences, an admin anyone's. Deleting a user is a soft delete (`deleted_at`): every read and update here ignores
soft-deleted users. Channel preferences answer 501 until their models change.
"""

import uuid

import structlog
from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth import service as auth_service
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.errors import Conflict, Forbidden, NotFound, NotImplementedYet
from pagercutie.core.schemas import Pagination
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole, UserCreate, UserRead, UserUpdate

_USER = "User"
_ACTIVE = User.deleted_at.is_(None)


# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_users(session: AsyncSession, pagination: Pagination) -> list[UserRead]:
    """Any authenticated user: routing UIs need to pick user recipients."""
    # UUIDv7 ids sort in creation order.
    users = await session.scalars(
        select(User).where(_ACTIVE).order_by(User.id).limit(pagination.limit).offset(pagination.offset)
    )
    return [UserRead.model_validate(user) for user in users]


async def create_user(session: AsyncSession, actor: CurrentUser, data: UserCreate) -> UserRead:
    """Admin only. Email is the login key (ADR-0024) and must be unique among active users."""
    _require_admin(actor)
    email = _normalize_email(data.email)
    # Targets the partial index ix_users_email, so a duplicate answers 409 without aborting the transaction.
    user = await session.scalar(
        insert(User)
        .values(**data.model_dump() | {"email": email})
        .on_conflict_do_nothing(index_elements=[User.email], index_where=_ACTIVE)
        .returning(User)
    )
    if user is None:
        raise Conflict(f"An active user with email {email} already exists")
    return UserRead.model_validate(user)


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> UserRead:
    """Any authenticated user."""
    user = await session.scalar(select(User).where(User.id == user_id, _ACTIVE))
    if user is None:
        raise NotFound(_USER, user_id)
    return UserRead.model_validate(user)


async def update_user(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, data: UserUpdate) -> UserRead:
    """The user themselves, or an admin. Only admins may change `role`."""
    _require_self_or_admin(actor, user_id)
    if data.role is not None and actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Only admins can change a user's role")
    # Omitted or null fields stay unchanged (UserUpdate docstring).
    changes = data.model_dump(exclude_none=True)
    if changes:
        user = await session.scalar(update(User).where(User.id == user_id, _ACTIVE).values(**changes).returning(User))
    else:
        user = await session.scalar(select(User).where(User.id == user_id, _ACTIVE))
    if user is None:
        raise NotFound(_USER, user_id)
    return UserRead.model_validate(user)


async def delete_user(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID) -> None:
    """Admin only. Soft delete: logs the user out everywhere; team memberships and rotation slots stay."""
    _require_admin(actor)
    deleted_id = await session.scalar(
        update(User).where(User.id == user_id, _ACTIVE).values(deleted_at=func.now()).returning(User.id)
    )
    # Only active users match, so deleting twice is a 404.
    if deleted_id is None:
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


log = structlog.get_logger("users")


async def bootstrap_admin(session: AsyncSession, email: str) -> bool:
    """Make `email` an admin, creating the user if needed, unless an admin already exists. True if it wrote one."""
    if await session.scalar(select(exists().where(User.role == GlobalRole.ADMIN))):
        return False
    email = email.lower()
    statement = insert(User).values(
        email=email,
        display_name=email.partition("@")[0],
        timezone="UTC",
        role=GlobalRole.ADMIN,
        channel_preferences=ChannelPreferences(),
    )
    # The upsert promotes an existing user, and lets API replicas starting together write the same row safely.
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[User.email],
            index_where=User.deleted_at.is_(None),
            set_={"role": GlobalRole.ADMIN},
        )
    )
    log.info("users.admin_bootstrapped", email=email)
    return True
