from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyCookie

from pagercutie.auth import service
from pagercutie.auth.service import CurrentUser
from pagercutie.core.deps import SessionDep
from pagercutie.core.errors import Unauthenticated
from pagercutie.core.schemas import error_responses

SESSION_COOKIE = "pc_session"

# A cookie, not a header: the live feed uses EventSource, which cannot send headers.
session_cookie = APIKeyCookie(name=SESSION_COOKIE, auto_error=False, description="Set by POST /auth/login")


async def get_current_user(
    session: SessionDep, session_id: Annotated[str | None, Security(session_cookie)]
) -> CurrentUser:
    """Resolves the `pc_session` cookie; raises `Unauthenticated` when it is missing, unknown or expired."""
    if not session_id:
        raise Unauthenticated()
    return await service.authenticate(session, session_id)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]

# For routers whose every route needs a logged-in user:
# `APIRouter(..., dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)`.
AUTHENTICATED = [Depends(get_current_user)]
AUTHENTICATED_RESPONSES = error_responses(401)
