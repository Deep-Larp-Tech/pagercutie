import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth.models import UserSession
from pagercutie.auth.schemas import MembershipRead, MeRead
from pagercutie.core.errors import Unauthenticated, UserEmailNotFound
from pagercutie.core.tokens import hash_token, new_token
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRead, TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole, UserRead


@dataclass(frozen=True)
class CurrentUser:
    """The logged-in user behind a `pc_session` cookie."""

    id: uuid.UUID
    role: GlobalRole
    session_token_hash: bytes
    team_roles: dict[uuid.UUID, TeamRole] = field(default_factory=dict)

    @property
    def is_admin(self) -> bool:
        return self.role == GlobalRole.ADMIN

    def can_see_team(self, team_id: uuid.UUID) -> bool:
        """Any role in the team, or admin (DOMAIN §4)."""
        return self.is_admin or team_id in self.team_roles

    def can_edit_team(self, team_id: uuid.UUID) -> bool:
        """`member` or `lead` of the team, or admin: may change its rules, runbooks, sources, schemas (DOMAIN §4)."""
        return self.is_admin or self.team_roles.get(team_id) in {TeamRole.MEMBER, TeamRole.LEAD}


async def login(session: AsyncSession, email: str, ttl: timedelta) -> tuple[str, MeRead]:
    """Creates a session for the user with this email; returns the cookie value and the user."""
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        raise UserEmailNotFound(email)
    token = new_token()
    session.add(UserSession(token_hash=hash_token(token), user_id=user.id, expires_at=datetime.now(UTC) + ttl))
    await session.flush()
    return token, await get_me(session, user.id)


async def logout(session: AsyncSession, token_hash: bytes) -> None:
    await session.execute(delete(UserSession).where(UserSession.token_hash == token_hash))


async def authenticate(session: AsyncSession, token: str) -> CurrentUser:
    """The user behind an unexpired session token."""
    token_hash = hash_token(token)
    row = (
        await session.execute(
            select(User.id, User.role)
            .join(UserSession, UserSession.user_id == User.id)
            .where(UserSession.token_hash == token_hash, UserSession.expires_at > datetime.now(UTC))
        )
    ).one_or_none()
    if row is None:
        raise Unauthenticated()
    memberships = await session.execute(select(Membership.team_id, Membership.role).where(Membership.user_id == row.id))
    return CurrentUser(
        id=row.id,
        role=row.role,
        session_token_hash=token_hash,
        team_roles={team_id: role for team_id, role in memberships},
    )


async def revoke_user_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Deletes every login session of the user, so each of their cookies stops working."""
    await session.execute(delete(UserSession).where(UserSession.user_id == user_id))


async def get_me(session: AsyncSession, user_id: uuid.UUID) -> MeRead:
    user = await session.get_one(User, user_id)
    rows = await session.execute(
        select(Team, Membership.role)
        .join(Membership, Membership.team_id == Team.id)
        .where(Membership.user_id == user_id)
        .order_by(Team.slug)
    )
    return MeRead(
        user=UserRead.model_validate(user),
        memberships=[MembershipRead(team=TeamRead.model_validate(team), role=role) for team, role in rows],
    )
