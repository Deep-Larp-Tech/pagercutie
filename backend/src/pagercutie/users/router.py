import uuid

from fastapi import APIRouter, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES
from pagercutie.core.deps import PaginationDep
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.users.schemas import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_users(pagination: PaginationDep) -> list[UserRead]:
    raise NotImplementedYet("Users")


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 409))
async def create_user(data: UserCreate) -> UserRead:
    """Admin only."""
    raise NotImplementedYet("Users")


@router.get("/{user_id}", responses=error_responses(404))
async def get_user(user_id: uuid.UUID) -> UserRead:
    raise NotImplementedYet("Users")


@router.patch("/{user_id}", responses=error_responses(400, 403, 404))
async def update_user(user_id: uuid.UUID, data: UserUpdate) -> UserRead:
    """The user themselves, or an admin."""
    raise NotImplementedYet("Users")


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404))
async def delete_user(user_id: uuid.UUID) -> None:
    """Admin only."""
    raise NotImplementedYet("Users")


@router.get("/{user_id}/channel-preferences", responses=error_responses(403, 404))
async def get_user_channel_preferences(user_id: uuid.UUID) -> ChannelPreferences:
    raise NotImplementedYet("Channel preferences")


@router.put("/{user_id}/channel-preferences", responses=error_responses(400, 403, 404))
async def set_user_channel_preferences(user_id: uuid.UUID, data: ChannelPreferences) -> ChannelPreferences:
    """The user themselves, or an admin."""
    raise NotImplementedYet("Channel preferences")
