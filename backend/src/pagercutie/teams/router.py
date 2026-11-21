import uuid

from fastapi import APIRouter, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES, CurrentUserDep
from pagercutie.core.deps import PaginationDep, SessionDep
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.teams import service
from pagercutie.teams.schemas import MemberRead, MembershipSet, OnCallRead, Rotation, TeamCreate, TeamRead, TeamUpdate

router = APIRouter(prefix="/teams", tags=["teams"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_teams(session: SessionDep, pagination: PaginationDep) -> list[TeamRead]:
    return await service.list_teams(session, pagination)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 409))
async def create_team(session: SessionDep, user: CurrentUserDep, data: TeamCreate) -> TeamRead:
    """Admin only."""
    return await service.create_team(session, user, data)


@router.get("/{team_id}", responses=error_responses(404))
async def get_team(session: SessionDep, team_id: uuid.UUID) -> TeamRead:
    return await service.get_team(session, team_id)


@router.patch("/{team_id}", responses=error_responses(400, 403, 404))
async def update_team(session: SessionDep, user: CurrentUserDep, team_id: uuid.UUID, data: TeamUpdate) -> TeamRead:
    """Team lead or admin."""
    return await service.update_team(session, user, team_id, data)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404, 409))
async def delete_team(session: SessionDep, user: CurrentUserDep, team_id: uuid.UUID) -> None:
    """Admin only. 409 while the team still owns rules, runbooks, sources or schemas."""
    await service.delete_team(session, user, team_id)


@router.get("/{team_id}/members", responses=error_responses(404))
async def list_team_members(session: SessionDep, user: CurrentUserDep, team_id: uuid.UUID) -> list[MemberRead]:
    return await service.list_members(session, user, team_id)


@router.put("/{team_id}/members/{user_id}", responses=error_responses(400, 403, 404))
async def set_team_member(
    session: SessionDep, user: CurrentUserDep, team_id: uuid.UUID, user_id: uuid.UUID, data: MembershipSet
) -> MemberRead:
    """Add a member or change their role. Team lead or admin."""
    return await service.set_member(session, user, team_id, user_id, data)


@router.delete(
    "/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404, 409)
)
async def remove_team_member(session: SessionDep, user: CurrentUserDep, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Team lead or admin. 409 when removing the last lead."""
    await service.remove_member(session, user, team_id, user_id)


@router.get("/{team_id}/channel-preferences", responses=error_responses(404))
async def get_team_channel_preferences(team_id: uuid.UUID) -> ChannelPreferences:
    raise NotImplementedYet("Channel preferences")


@router.put("/{team_id}/channel-preferences", responses=error_responses(400, 403, 404))
async def set_team_channel_preferences(team_id: uuid.UUID, data: ChannelPreferences) -> ChannelPreferences:
    """Team lead or admin."""
    raise NotImplementedYet("Channel preferences")


@router.get("/{team_id}/rotation", responses=error_responses(404))
async def get_team_rotation(session: SessionDep, user: CurrentUserDep, team_id: uuid.UUID) -> Rotation | None:
    return await service.get_rotation(session, user, team_id)


@router.put("/{team_id}/rotation", responses=error_responses(400, 403, 404))
async def set_team_rotation(session: SessionDep, user: CurrentUserDep, team_id: uuid.UUID, data: Rotation) -> Rotation:
    """Team lead or admin. Every user must be a lead or member of the team."""
    return await service.set_rotation(session, user, team_id, data)


@router.get("/{team_id}/on-call", responses=error_responses(404))
async def get_team_on_call(team_id: uuid.UUID) -> OnCallRead:
    raise NotImplementedYet("On-call")
