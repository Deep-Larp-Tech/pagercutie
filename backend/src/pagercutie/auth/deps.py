import uuid
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyCookie

from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.schemas import GlobalRole

SESSION_COOKIE = "pc_session"

# A cookie, not a header: the live feed uses EventSource, which cannot send headers.
session_cookie = APIKeyCookie(name=SESSION_COOKIE, auto_error=False, description="Set by POST /auth/login")


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    role: GlobalRole
    team_roles: dict[uuid.UUID, TeamRole] = field(default_factory=dict)


async def get_current_user(session_id: Annotated[str | None, Security(session_cookie)]) -> CurrentUser:
    """Resolves the `pc_session` cookie; raises `Unauthenticated` when it is missing or unknown."""
    # TODO: the session → user lookup must filter `users.deleted_at IS NULL`, so a soft-deleted user's stale cookie
    # fails like an unknown one.
    raise NotImplementedYet("Authentication")


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]

# For routers whose every route needs a logged-in user:
# `APIRouter(..., dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)`.
AUTHENTICATED = [Depends(get_current_user)]
AUTHENTICATED_RESPONSES = error_responses(401)
