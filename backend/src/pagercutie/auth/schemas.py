from pydantic import EmailStr

from pagercutie.core.schemas import InputModel, ReadModel
from pagercutie.teams.schemas import TeamRead, TeamRole
from pagercutie.users.schemas import UserRead


class LoginRequest(InputModel):
    """Demo login: no password (DOMAIN.md §2)."""

    email: EmailStr


class MembershipRead(ReadModel):
    team: TeamRead
    role: TeamRole


class MeRead(ReadModel):
    user: UserRead
    memberships: list[MembershipRead]
