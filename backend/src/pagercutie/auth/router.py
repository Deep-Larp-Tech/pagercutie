from typing import Annotated

from fastapi import APIRouter, Query, status

from pagercutie.alerts.schemas import DeliveryRead
from pagercutie.auth.deps import CurrentUserDep
from pagercutie.auth.schemas import LoginRequest, MeRead
from pagercutie.core.deps import PaginationDep
from pagercutie.core.enums import Channel
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses

router = APIRouter(tags=["auth"])


@router.post("/auth/login", responses=error_responses(404))
async def login(data: LoginRequest) -> MeRead:
    """Log in as the user with this email and set the `pc_session` cookie."""
    raise NotImplementedYet("Login")


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(401))
async def logout(user: CurrentUserDep) -> None:
    raise NotImplementedYet("Logout")


@router.get("/me", responses=error_responses(401))
async def get_me(user: CurrentUserDep) -> MeRead:
    raise NotImplementedYet("Current user")


@router.get("/me/messages", responses=error_responses(401))
async def list_my_messages(
    user: CurrentUserDep,
    pagination: PaginationDep,
    channel: Annotated[list[Channel] | None, Query()] = None,
) -> list[DeliveryRead]:
    """The current user's deliveries, newest first: the simulated phone panel uses `channel=sms&channel=phone`."""
    raise NotImplementedYet("Messages")
