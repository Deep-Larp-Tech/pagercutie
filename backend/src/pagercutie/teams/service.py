"""Teams, memberships and on-call rotations.

Permissions follow DOMAIN.md §4: any authenticated user reads teams (they are routing and escalation targets); any
role in a team reads its members and rotation, and a team the actor is not in answers 404; admins create and delete
teams; a team lead or an admin edits the team, its memberships and its
rotation. Every team keeps at least one active lead once it has one: removing the last lead answers 409 and demoting
them answers 422. Channel preferences (pending their model review, ADR-0038) and on-call still answer 501.
"""

import uuid

from sqlalchemy import delete, exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth.deps import CurrentUser
from pagercutie.core.errors import Conflict, FieldError, Forbidden, InvalidInput, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.event_schemas.models import EventSchema
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.rules.models import Rule
from pagercutie.runbooks.models import Runbook
from pagercutie.sources.models import Source
from pagercutie.teams.models import Membership, RotationMember, Team
from pagercutie.teams.models import Rotation as RotationRow
from pagercutie.teams.schemas import (
    MemberRead,
    MembershipSet,
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
    # A raw insert bypasses the ORM default, so the empty preferences are explicit (ADR-0038).
    team = await session.scalar(
        insert(Team)
        .values(**data.model_dump(), channel_preferences=ChannelPreferences())
        .on_conflict_do_nothing(index_elements=[Team.slug])
        .returning(Team)
    )
    if team is None:
        raise Conflict(f"A team with slug {data.slug} already exists")
    return TeamRead.model_validate(team)


async def get_team(session: AsyncSession, team_id: uuid.UUID) -> TeamRead:
    """Any authenticated user."""
    team = await session.scalar(select(Team).where(Team.id == team_id))
    if team is None:
        raise NotFound(_TEAM, team_id)
    return TeamRead.model_validate(team)


async def update_team(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID, data: TeamUpdate) -> TeamRead:
    """Team lead or admin."""
    _require_lead_or_admin(actor, team_id)
    # Omitted or null fields stay unchanged (TeamUpdate docstring).
    changes = data.model_dump(exclude_none=True)
    if changes:
        team = await session.scalar(update(Team).where(Team.id == team_id).values(**changes).returning(Team))
    else:
        team = await session.scalar(select(Team).where(Team.id == team_id))
    if team is None:
        raise NotFound(_TEAM, team_id)
    return TeamRead.model_validate(team)


async def delete_team(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID) -> None:
    """Admin only. 409 while the team owns sources, event schemas, rules or runbooks."""
    _require_admin(actor)
    await _lock_team(session, team_id)
    # The foreign keys are RESTRICT, so the owned entities are counted here instead of surfacing as a 500.
    for owned in (Source, EventSchema, Rule, Runbook):
        if await session.scalar(select(exists().where(owned.team_id == team_id))):
            raise Conflict(f"Team {team_id} still owns {owned.__tablename__}")
    await session.execute(delete(Team).where(Team.id == team_id))


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
    await session.execute(
        insert(Membership)
        .values(team_id=team_id, user_id=user_id, role=data.role)
        .on_conflict_do_update(index_elements=[Membership.team_id, Membership.user_id], set_={"role": data.role})
    )
    return MemberRead(user=UserRead.model_validate(user), role=data.role)


async def remove_member(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Team lead or admin. 409 when removing the last lead. The user's rotation slots stay."""
    _require_lead_or_admin(actor, team_id)
    await _lock_team(session, team_id)
    if await _is_last_lead(session, team_id, user_id):
        raise Conflict("Cannot remove the last lead of a team")
    removed = await session.scalar(
        delete(Membership)
        .where(Membership.team_id == team_id, Membership.user_id == user_id)
        .returning(Membership.user_id)
    )
    if removed is None:
        raise NotFound(_MEMBERSHIP, user_id)


async def get_rotation(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID) -> Rotation | None:
    """Any role in the team, or an admin. None when the team has no rotation."""
    await _require_visible_team(session, actor, team_id)
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


async def set_rotation(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID, data: Rotation) -> Rotation:
    """Team lead or admin. Replaces the rotation and restarts it with `user_ids[0]` now (DEL-3)."""
    _require_lead_or_admin(actor, team_id)
    await _lock_team(session, team_id)
    await _require_rotation_users(session, team_id, data.user_ids)
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
    return data


# --- Rules -----------------------------------------------------------------------------------------------------


def _require_admin(actor: CurrentUser) -> None:
    if actor.role is not GlobalRole.ADMIN:
        raise Forbidden("Admin only")


def _require_lead_or_admin(actor: CurrentUser, team_id: uuid.UUID) -> None:
    # Checked before any DB access so non-members can't probe which team IDs exist.
    if actor.role is not GlobalRole.ADMIN and actor.team_roles.get(team_id) is not TeamRole.LEAD:
        raise Forbidden("Only a team lead or an admin can do this")


async def _require_visible_team(session: AsyncSession, actor: CurrentUser, team_id: uuid.UUID) -> None:
    # 404, not 403: the routes declare no 403, and non-members can't tell a hidden team's roster from a missing team.
    if actor.role is not GlobalRole.ADMIN and team_id not in actor.team_roles:
        raise NotFound(_TEAM, team_id)
    if await session.scalar(select(Team.id).where(Team.id == team_id)) is None:
        raise NotFound(_TEAM, team_id)


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
