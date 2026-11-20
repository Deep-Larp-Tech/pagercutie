from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from pagercutie.alerts.schemas import DeliveryRead
from pagercutie.auth import service
from pagercutie.auth.deps import SESSION_COOKIE, CurrentUserDep
from pagercutie.auth.schemas import LoginRequest, MeRead
from pagercutie.core.deps import PaginationDep, SessionDep, SettingsDep
from pagercutie.core.enums import Channel
from pagercutie.core.schemas import error_responses

router = APIRouter(tags=["auth"])


@router.post("/auth/login", responses=error_responses(404))
async def login(data: LoginRequest, session: SessionDep, settings: SettingsDep, response: Response) -> MeRead:
    """Log in as the user with this email and set the `pc_session` cookie."""
    token, me = await service.login(session, data.email, settings.session_ttl)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(settings.session_ttl.total_seconds()),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return me


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(401))
async def logout(user: CurrentUserDep, session: SessionDep, settings: SettingsDep, response: Response) -> None:
    await service.logout(session, user.session_token_hash)
    response.delete_cookie(SESSION_COOKIE, httponly=True, secure=settings.session_cookie_secure, samesite="lax")


@router.get("/me", responses=error_responses(401))
async def get_me(user: CurrentUserDep, session: SessionDep) -> MeRead:
    return await service.get_me(session, user.id)


@router.get("/me/messages", responses=error_responses(401))
async def list_my_messages(
    user: CurrentUserDep,
    session: SessionDep,
    pagination: PaginationDep,
    channel: Annotated[list[Channel] | None, Query()] = None,
) -> list[DeliveryRead]:
    """The current user's deliveries, newest first: the simulated phone panel uses `channel=sms&channel=phone`."""
    return await service.list_messages(session, user.id, pagination, channel)
