import uuid

from fastapi import APIRouter, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES
from pagercutie.core.deps import PaginationDep
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.teams.schemas import MemberRead, MembershipSet, OnCallRead, Rotation, TeamCreate, TeamRead, TeamUpdate

router = APIRouter(prefix="/teams", tags=["teams"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_teams(pagination: PaginationDep) -> list[TeamRead]:
    raise NotImplementedYet("Teams")


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 409))
async def create_team(data: TeamCreate) -> TeamRead:
    """Admin only."""
    raise NotImplementedYet("Teams")


@router.get("/{team_id}", responses=error_responses(404))
async def get_team(team_id: uuid.UUID) -> TeamRead:
    raise NotImplementedYet("Teams")


@router.patch("/{team_id}", responses=error_responses(400, 403, 404))
async def update_team(team_id: uuid.UUID, data: TeamUpdate) -> TeamRead:
    """Team lead or admin."""
    raise NotImplementedYet("Teams")


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404, 409))
async def delete_team(team_id: uuid.UUID) -> None:
    """Admin only. 409 while the team still owns rules, runbooks, sources or schemas."""
    raise NotImplementedYet("Teams")


@router.get("/{team_id}/members", responses=error_responses(404))
async def list_team_members(team_id: uuid.UUID) -> list[MemberRead]:
    raise NotImplementedYet("Team members")


@router.put("/{team_id}/members/{user_id}", responses=error_responses(400, 403, 404))
async def set_team_member(team_id: uuid.UUID, user_id: uuid.UUID, data: MembershipSet) -> MemberRead:
    """Add a member or change their role. Team lead or admin."""
    raise NotImplementedYet("Team members")


@router.delete(
    "/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404, 409)
)
async def remove_team_member(team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Team lead or admin. 409 when removing the last lead."""
    raise NotImplementedYet("Team members")


@router.get("/{team_id}/channel-preferences", responses=error_responses(404))
async def get_team_channel_preferences(team_id: uuid.UUID) -> ChannelPreferences:
    raise NotImplementedYet("Channel preferences")


@router.put("/{team_id}/channel-preferences", responses=error_responses(400, 403, 404))
async def set_team_channel_preferences(team_id: uuid.UUID, data: ChannelPreferences) -> ChannelPreferences:
    """Team lead or admin."""
    raise NotImplementedYet("Channel preferences")


@router.get("/{team_id}/rotation", responses=error_responses(404))
async def get_team_rotation(team_id: uuid.UUID) -> Rotation | None:
    raise NotImplementedYet("Rotation")


@router.put("/{team_id}/rotation", responses=error_responses(400, 403, 404))
async def set_team_rotation(team_id: uuid.UUID, data: Rotation) -> Rotation:
    """Team lead or admin. Every user must be a lead or member of the team."""
    raise NotImplementedYet("Rotation")


@router.get("/{team_id}/on-call", responses=error_responses(404))
async def get_team_on_call(team_id: uuid.UUID) -> OnCallRead:
    raise NotImplementedYet("On-call")
