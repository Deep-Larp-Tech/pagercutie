"""Teams, memberships and on-call rotations.

Permissions follow DOMAIN.md §4: any authenticated user reads teams (they are routing and escalation targets); any
role in a team reads its members and rotation, and a team the actor is not in answers 404; admins create and delete
teams; a team lead or an admin edits the team, its channel preferences, its memberships and its rotation. Any role in
a team reads its channel preferences and on-call user. Every team keeps at least one active lead once it has one:
removing the last lead answers 409 and demoting them answers 422.
"""

import uuid
from datetime import UTC, datetime

from pydantic import JsonValue
from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pagercutie.alerts.models import RunbookRun
from pagercutie.audit import service as audit
from pagercutie.audit.schemas import AuditAction
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.db import violates_unique
from pagercutie.core.errors import Conflict, FieldError, Forbidden, InvalidInput, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.event_schemas.models import EventSchema
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.rules.models import Rule
from pagercutie.runbooks.models import Runbook
from pagercutie.sources.models import Source
from pagercutie.teams.models import Membership, RotationMember, Team
from pagercutie.teams.models import Rotation as RotationRow
from pagercutie.teams.rotation import on_call_at
from pagercutie.teams.schemas import (
    MemberRead,
    MembershipSet,
    OnCallRead,
    Rotation,
    TeamCreate,
    TeamRead,
    TeamRole,
    TeamUpdate,
)
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole, UserRead

_TEAM = "Team"
_USER = "User"
_MEMBERSHIP = "Membership"
_ACTIVE = User.deleted_at.is_(None)
_ROTATION_ROLES = (TeamRole.LEAD, TeamRole.MEMBER)


# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_teams(session: AsyncSession, pagination: Pagination) -> list[TeamRead]:
    """Any authenticated user."""
    # UUIDv7 ids sort in creation order.
    teams = await session.scalars(select(Team).order_by(Team.id).limit(pagination.limit).offset(pagination.offset))
    return [TeamRead.model_validate(team) for team in teams]


async def create_team(session: AsyncSession, actor: CurrentUser, data: TeamCreate) -> TeamRead:
    """Admin only. The slug is unique and permanent."""
    _require_admin(actor)
    team = Team(slug=data.slug, name=data.name, description=data.description)
    session.add(team)
    # No savepoint needed: the Conflict rolls back the request's transaction.
    try:
        await session.flush()
    except IntegrityError as error:
        if violates_unique(error, "uq_teams_slug"):
            raise Conflict(f"A team with slug {data.slug} already exists") from None
        raise
    created = TeamRead.model_validate(team)
    audit.record(session, actor.id, AuditAction.TEAM_CREATED, team.id, team.id, _identity(created))
    return created


async def get_team(session: AsyncSession, team_id: uuid.UUID) -> TeamRead:
    """Any authenticated user."""
    team = await _get_team(session, team_id)
    return TeamRead.model_validate(team)


async def update_team(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID, data: TeamUpdate) -> TeamRead:
    """Team lead or admin."""
    _require_lead_or_admin(actor, team_id)
    team = await _get_team(session, team_id)
    before = _identity(TeamRead.model_validate(team))
    # Omitted or null fields stay unchanged (TeamUpdate docstring).
    if data.name is not None:
        team.name = data.name
    if data.description is not None:
        team.description = data.description
    await session.flush()
    updated = TeamRead.model_validate(team)
    diff = audit.changes(before, _identity(updated))
    if diff["after"]:
        audit.record(session, actor.id, AuditAction.TEAM_UPDATED, team_id, team_id, diff)
    return updated


async def delete_team(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID) -> None:
    """Admin only. 409 while the team owns sources, event schemas, rules, runbooks, or deleted runbooks with runs.

    Soft-deleted runbooks without runs are removed with the team.
    """
    _require_admin(actor)
    await _lock_team(session, team_id)
    # The foreign keys are RESTRICT, so the owned entities are counted here instead of surfacing as a 500.
    for owned in (Source, EventSchema, Rule):
        if await session.scalar(select(exists().where(owned.team_id == team_id))):
            raise Conflict(f"Team {team_id} still owns {owned.__tablename__}")
    if await session.scalar(select(exists().where(Runbook.team_id == team_id, Runbook.deleted_at.is_(None)))):
        raise Conflict(f"Team {team_id} still owns runbooks")
    deleted_runbooks = select(Runbook.id).where(Runbook.team_id == team_id)
    if await session.scalar(select(exists().where(RunbookRun.runbook_id.in_(deleted_runbooks)))):
        raise Conflict(f"Team {team_id} owns deleted runbooks that have runs")
    await session.execute(delete(Runbook).where(Runbook.team_id == team_id))
    deleted = (await session.execute(delete(Team).where(Team.id == team_id).returning(Team.slug, Team.name))).one()
    data: dict[str, JsonValue] = {"slug": deleted.slug, "name": deleted.name}
    audit.record(session, actor.id, AuditAction.TEAM_DELETED, team_id, team_id, data)


async def list_members(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID) -> list[MemberRead]:
    """Any role in the team, or an admin. Soft-deleted users are left out."""
    await _require_visible_team(session, actor, team_id)
    rows = await session.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.team_id == team_id, _ACTIVE)
        .order_by(User.id)
    )
    return [MemberRead(user=UserRead.model_validate(user), role=role) for user, role in rows]


async def set_member(
    session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID, user_id: uuid.UUID, data: MembershipSet
) -> MemberRead:
    """Team lead or admin. Adds the membership or changes its role; demoting the last lead is rejected."""
    _require_lead_or_admin(actor, team_id)
    await _lock_team(session, team_id)
    user = await session.scalar(select(User).where(User.id == user_id, _ACTIVE))
    if user is None:
        raise NotFound(_USER, user_id)
    if data.role is not TeamRole.LEAD and await _is_last_lead(session, team_id, user_id):
        raise InvalidInput([FieldError(loc=("role",), msg="A team needs at least one lead")])
    # The team lock serialises membership writers, so the role read here is the one the upsert replaces.
    previous = await session.scalar(
        select(Membership.role).where(Membership.team_id == team_id, Membership.user_id == user_id)
    )
    await session.execute(
        insert(Membership)
        .values(team_id=team_id, user_id=user_id, role=data.role)
        .on_conflict_do_update(index_elements=[Membership.team_id, Membership.user_id], set_={"role": data.role})
    )
    if previous is None:
        added: dict[str, JsonValue] = {"user_id": str(user_id), "role": data.role.value}
        audit.record(session, actor.id, AuditAction.TEAM_MEMBER_ADDED, team_id, team_id, added)
    elif previous is not data.role:
        changed: dict[str, JsonValue] = {
            "user_id": str(user_id),
            "before": {"role": previous.value},
            "after": {"role": data.role.value},
        }
        audit.record(session, actor.id, AuditAction.TEAM_MEMBER_ROLE_CHANGED, team_id, team_id, changed)
    return MemberRead(user=UserRead.model_validate(user), role=data.role)


async def remove_member(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Team lead or admin. 409 when removing the last lead. The user's rotation slots stay."""
    _require_lead_or_admin(actor, team_id)
    await _lock_team(session, team_id)
    if await _is_last_lead(session, team_id, user_id):
        raise Conflict("Cannot remove the last lead of a team")
    removed_role = await session.scalar(
        delete(Membership)
        .where(Membership.team_id == team_id, Membership.user_id == user_id)
        .returning(Membership.role)
    )
    if removed_role is None:
        raise NotFound(_MEMBERSHIP, user_id)
    removed: dict[str, JsonValue] = {"user_id": str(user_id), "role": removed_role.value}
    audit.record(session, actor.id, AuditAction.TEAM_MEMBER_REMOVED, team_id, team_id, removed)


async def get_channel_preferences(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID) -> ChannelPreferences:
    """Any role in the team, or an admin."""
    _require_member_or_admin(actor, team_id)
    team = await _get_team(session, team_id)
    return team.channel_preferences


async def set_channel_preferences(
    session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID, data: ChannelPreferences
) -> ChannelPreferences:
    """Team lead or admin. PUT replaces the whole value object."""
    _require_lead_or_admin(actor, team_id)
    team = await _get_team(session, team_id)
    before = team.channel_preferences.model_dump(mode="json")
    # Typed assignment (ADR-0058); PydanticJSONB tracks reassignment only, not in-place mutation.
    team.channel_preferences = data
    await session.flush()
    diff: dict[str, JsonValue] = {"before": before, "after": data.model_dump(mode="json")}
    audit.record(session, actor.id, AuditAction.TEAM_CHANNEL_PREFERENCES_UPDATED, team_id, team_id, diff)
    return team.channel_preferences


async def get_rotation(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID) -> Rotation | None:
    """Any role in the team, or an admin. None when the team has no rotation."""
    await _require_visible_team(session, actor, team_id)
    return await _read_rotation(session, team_id)


async def set_rotation(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID, data: Rotation) -> Rotation:
    """Team lead or admin. Replaces the rotation and restarts it with `user_ids[0]` now (DEL-3)."""
    _require_lead_or_admin(actor, team_id)
    await _lock_team(session, team_id)
    await _require_rotation_users(session, team_id, data.user_ids)
    previous = await _read_rotation(session, team_id)
    # Deleting the rotation row cascades to its members.
    await session.execute(delete(RotationRow).where(RotationRow.team_id == team_id))
    await session.execute(
        insert(RotationRow).values(
            team_id=team_id, handoff_day=data.handoff_day, handoff_time=data.handoff_time, timezone=data.timezone
        )
    )
    await session.execute(
        insert(RotationMember),
        [{"team_id": team_id, "position": position, "user_id": uid} for position, uid in enumerate(data.user_ids)],
    )
    diff: dict[str, JsonValue] = {
        "before": None if previous is None else previous.model_dump(mode="json"),
        "after": data.model_dump(mode="json"),
    }
    audit.record(session, actor.id, AuditAction.TEAM_ROTATION_UPDATED, team_id, team_id, diff)
    return data


async def get_on_call(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID) -> OnCallRead:
    """Any role in the team, or an admin. `user` and `until` are null without a rotation.

    `user` is also null when the person on call is soft-deleted (ADR-0057); their slot stays in the rotation, so
    `until` still names the handoff.
    """
    await _require_visible_team(session, actor, team_id)
    # populate_existing: the session may hold a rotation that `set_rotation` has since replaced with Core statements.
    rotation = await session.scalar(
        select(RotationRow)
        .where(RotationRow.team_id == team_id)
        .options(selectinload(RotationRow.members))
        .execution_options(populate_existing=True)
    )
    on_call = None if rotation is None else on_call_at(rotation, datetime.now(UTC))
    if on_call is None:
        return OnCallRead(team_id=team_id, user=None, until=None)
    user = await session.scalar(select(User).where(User.id == on_call.user_id, _ACTIVE))
    return OnCallRead(
        team_id=team_id, user=None if user is None else UserRead.model_validate(user), until=on_call.until
    )


async def _read_rotation(session: AsyncSession, team_id: uuid.UUID) -> Rotation | None:
    # Columns, not entities: rows are not cached in the identity map, so a replaced rotation is never read stale.
    schedule = (
        await session.execute(
            select(RotationRow.handoff_day, RotationRow.handoff_time, RotationRow.timezone).where(
                RotationRow.team_id == team_id
            )
        )
    ).one_or_none()
    if schedule is None:
        return None
    user_ids = await session.scalars(
        select(RotationMember.user_id).where(RotationMember.team_id == team_id).order_by(RotationMember.position)
    )
    return Rotation(
        user_ids=list(user_ids),
        handoff_day=schedule.handoff_day,
        handoff_time=schedule.handoff_time,
        timezone=schedule.timezone,
    )


def _identity(team: TeamRead) -> dict[str, JsonValue]:
    return team.model_dump(mode="json", include={"slug", "name", "description"})


# --- Rules -----------------------------------------------------------------------------------------------------


def _require_admin(actor: CurrentUser) -> None:
    if actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Admin only")


def _require_lead_or_admin(actor: CurrentUser, team_id: uuid.UUID) -> None:
    # Checked before any DB access so non-members can't probe which team IDs exist.
    if actor.role is not GlobalRole.ADMIN and actor.team_roles.get(team_id) is not TeamRole.LEAD:
        raise Forbidden("Only a team lead or an admin can do this")


def _require_member_or_admin(actor: CurrentUser, team_id: uuid.UUID) -> None:
    # 404, not 403: the routes declare no 403, and non-members can't tell a hidden team's roster from a missing team.
    if actor.role is not GlobalRole.ADMIN and team_id not in actor.team_roles:
        raise NotFound(_TEAM, team_id)


async def _require_visible_team(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID) -> None:
    _require_member_or_admin(actor, team_id)
    if await session.scalar(select(Team.id).where(Team.id == team_id)) is None:
        raise NotFound(_TEAM, team_id)


async def _get_team(session: AsyncSession, team_id: uuid.UUID) -> Team:
    team = await session.scalar(select(Team).where(Team.id == team_id))
    if team is None:
        raise NotFound(_TEAM, team_id)
    return team


async def _lock_team(session: AsyncSession, team_id: uuid.UUID) -> None:
    """Raises `NotFound` for a missing team and serialises writers of the team's memberships and rotation."""
    if await session.scalar(select(Team.id).where(Team.id == team_id).with_for_update()) is None:
        raise NotFound(_TEAM, team_id)


async def _is_last_lead(session: AsyncSession, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """True when `user_id` leads the team and no other active user does."""
    is_lead = await session.scalar(
        select(
            exists().where(
                Membership.team_id == team_id, Membership.user_id == user_id, Membership.role == TeamRole.LEAD
            )
        )
    )
    if not is_lead:
        return False
    other_lead = await session.scalar(
        select(
            exists().where(
                Membership.team_id == team_id,
                Membership.user_id != user_id,
                Membership.role == TeamRole.LEAD,
                Membership.user_id == User.id,
                _ACTIVE,
            )
        )
    )
    return not other_lead


async def _require_rotation_users(session: AsyncSession, team_id: uuid.UUID, user_ids: list[uuid.UUID]) -> None:
    """Every rotation slot needs an active lead or member of the team."""
    eligible = set(
        await session.scalars(
            select(Membership.user_id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.team_id == team_id,
                Membership.role.in_(_ROTATION_ROLES),
                Membership.user_id.in_(user_ids),
                _ACTIVE,
            )
        )
    )
    errors = [
        FieldError(loc=("user_ids", index), msg=f"User {uid} is not an active lead or member of the team")
        for index, uid in enumerate(user_ids)
        if uid not in eligible
    ]
    if errors:
        raise InvalidInput(errors)
