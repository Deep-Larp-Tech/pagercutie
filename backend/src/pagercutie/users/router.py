import uuid

from fastapi import APIRouter, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES, CurrentUserDep
from pagercutie.core.deps import PaginationDep, SessionDep
from pagercutie.core.schemas import error_responses
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.users import service
from pagercutie.users.schemas import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_users(session: SessionDep, pagination: PaginationDep) -> list[UserRead]:
    return await service.list_users(session, pagination)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 409))
async def create_user(session: SessionDep, user: CurrentUserDep, data: UserCreate) -> UserRead:
    """Admin only."""
    return await service.create_user(session, user, data)


@router.get("/{user_id}", responses=error_responses(404))
async def get_user(session: SessionDep, user_id: uuid.UUID) -> UserRead:
    return await service.get_user(session, user_id)


@router.patch("/{user_id}", responses=error_responses(400, 403, 404))
async def update_user(session: SessionDep, user: CurrentUserDep, user_id: uuid.UUID, data: UserUpdate) -> UserRead:
    """The user themselves, or an admin."""
    return await service.update_user(session, user, user_id, data)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404))
async def delete_user(session: SessionDep, user: CurrentUserDep, user_id: uuid.UUID) -> None:
    """Admin only."""
    await service.delete_user(session, user, user_id)


@router.get("/{user_id}/channel-preferences", responses=error_responses(403, 404))
async def get_user_channel_preferences(
    session: SessionDep, user: CurrentUserDep, user_id: uuid.UUID
) -> ChannelPreferences:
    return await service.get_channel_preferences(session, user, user_id)


@router.put("/{user_id}/channel-preferences", responses=error_responses(400, 403, 404))
async def set_user_channel_preferences(
    session: SessionDep, user: CurrentUserDep, user_id: uuid.UUID, data: ChannelPreferences
) -> ChannelPreferences:
    """The user themselves, or an admin."""
    return await service.set_channel_preferences(session, user, user_id, data)
