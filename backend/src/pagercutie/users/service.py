"""Users and per-user channel preferences.

Permissions follow DOMAIN.md §4: admins create, delete and re-role users; a user edits their own profile and
preferences, an admin anyone's. Deleting a user is a soft delete (`deleted_at`): every read and update here ignores
soft-deleted users.
"""

import uuid

import structlog
from pydantic import JsonValue
from sqlalchemy import String, exists, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit import service as audit
from pagercutie.audit.schemas import AuditAction
from pagercutie.auth import service as auth_service
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.db import NotifyChannel, notify, violates_unique
from pagercutie.core.errors import Conflict, Forbidden, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole, UserCreate, UserRead, UserUpdate

_USER = "User"
_ACTIVE = User.deleted_at.is_(None)


async def list_users(session: AsyncSession, pagination: Pagination) -> list[UserRead]:
    """Any authenticated user: routing UIs need to pick user recipients."""
    users = await session.scalars(
        select(User).where(_ACTIVE).order_by(User.id).limit(pagination.limit).offset(pagination.offset)
    )
    return [UserRead.model_validate(user) for user in users]


async def create_user(session: AsyncSession, actor: CurrentUser, data: UserCreate) -> UserRead:
    """Admin only. Email is the login key (ADR-0024) and must be unique among active users."""
    _require_admin(actor)
    email = _normalize_email(data.email)
    user = User(email=email, display_name=data.display_name, phone=data.phone, timezone=data.timezone, role=data.role)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as error:
        if violates_unique(error, "ix_users_email"):
            raise Conflict(f"An active user with email {email} already exists") from None
        raise
    created = UserRead.model_validate(user)
    audit.record(session, actor.id, AuditAction.USER_CREATED, user.id, None, _identity(created))
    return created


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> UserRead:
    """Any authenticated user."""
    user = await _get_active_user(session, user_id)
    return UserRead.model_validate(user)


async def update_user(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, data: UserUpdate) -> UserRead:
    """The user themselves, or an admin. Only admins may change `role`."""
    _require_self_or_admin(actor, user_id)
    if data.role is not None and actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Only admins can change a user's role")
    user = await _get_active_user(session, user_id)
    before = _audited(UserRead.model_validate(user))
    previous_role = user.role
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.phone is not None:
        user.phone = data.phone
    if data.timezone is not None:
        user.timezone = data.timezone
    if data.role is not None:
        user.role = data.role
    await session.flush()
    updated = UserRead.model_validate(user)
    diff = audit.changes(before, _audited(updated))
    if diff["after"]:
        audit.record(session, actor.id, AuditAction.USER_UPDATED, user_id, None, diff)
    if user.role is not previous_role:
        await notify(session, NotifyChannel.ACCESS_CHANGED)
    return updated


async def delete_user(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID) -> None:
    """Admin only. Soft delete: logs the user out everywhere; team memberships and rotation slots stay."""
    _require_admin(actor)
    deleted = (
        await session.execute(
            update(User)
            .where(User.id == user_id, _ACTIVE)
            .values(deleted_at=func.now())
            .returning(User.email, User.display_name)
        )
    ).one_or_none()
    if deleted is None:
        raise NotFound(_USER, user_id)
    await auth_service.revoke_user_sessions(session, user_id)
    audit.record(
        session,
        actor.id,
        AuditAction.USER_DELETED,
        user_id,
        None,
        {"email": deleted.email, "display_name": deleted.display_name},
    )
    await notify(session, NotifyChannel.ACCESS_CHANGED)


async def get_channel_preferences(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID) -> ChannelPreferences:
    """The user themselves, or an admin. A new user has empty rules, i.e. UI only (DEL-2, ADR-0027)."""
    _require_self_or_admin(actor, user_id)
    user = await _get_active_user(session, user_id)
    return user.channel_preferences


async def set_channel_preferences(
    session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, data: ChannelPreferences
) -> ChannelPreferences:
    """The user themselves, or an admin. PUT replaces the whole value object."""
    _require_self_or_admin(actor, user_id)
    user = await _get_active_user(session, user_id)
    before = user.channel_preferences.model_dump(mode="json")
    user.channel_preferences = data
    await session.flush()
    audit.record(
        session,
        actor.id,
        AuditAction.USER_CHANNEL_PREFERENCES_UPDATED,
        user_id,
        None,
        {"before": before, "after": data.model_dump(mode="json")},
    )
    return user.channel_preferences


def _require_admin(actor: CurrentUser) -> None:
    if actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Admin only")


def _require_self_or_admin(actor: CurrentUser, user_id: uuid.UUID) -> None:
    if actor.id != user_id and actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Only the user themselves or an admin can do this")


async def _get_active_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.scalar(select(User).where(User.id == user_id, _ACTIVE))
    if user is None:
        raise NotFound(_USER, user_id)
    return user


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _audited(user: UserRead) -> dict[str, JsonValue]:
    """The profile fields an update can change, as audit data."""
    return user.model_dump(mode="json", include={"display_name", "phone", "timezone", "role"})


def _identity(user: UserRead) -> dict[str, JsonValue]:
    return user.model_dump(mode="json", include={"email", "display_name", "role"})


log = structlog.get_logger("users")


async def bootstrap_admin(session: AsyncSession, email: str) -> bool:
    """Make `email` an admin, creating the user if needed, unless an admin already exists. True if it wrote one."""
    if await session.scalar(select(exists().where(User.role == GlobalRole.ADMIN, _ACTIVE))):
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
    user_id, previous_role = (
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[User.email],
                index_where=User.deleted_at.is_(None),
                set_={"role": GlobalRole.ADMIN},
            ).returning(
                User.id,
                # Postgres 18: the row before the update, NULL after an insert.
                literal_column("old.role", String()),
            )
        )
    ).one()
    if previous_role is None:
        data: dict[str, JsonValue] = {"email": email, "role": GlobalRole.ADMIN.value}
        audit.record(session, None, AuditAction.USER_CREATED, user_id, None, data)
    else:
        diff: dict[str, JsonValue] = {"before": {"role": previous_role}, "after": {"role": GlobalRole.ADMIN.value}}
        audit.record(session, None, AuditAction.USER_UPDATED, user_id, None, diff)
    log.info("users.admin_bootstrapped", email=email)
    return True
