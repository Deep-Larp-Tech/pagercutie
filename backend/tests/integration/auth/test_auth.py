from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth.models import UserSession
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


@pytest.fixture
async def anna(session: AsyncSession) -> User:
    user = User(email="anna@example.com", display_name="Anna", timezone="Europe/Prague", role=GlobalRole.USER)
    team = Team(slug="payments", name="Payments")
    session.add_all([user, team])
    await session.flush()
    session.add(Membership(team_id=team.id, user_id=user.id, role=TeamRole.LEAD))
    await session.flush()
    return user


async def test_login_sets_an_http_only_cookie_and_returns_the_user(client: AsyncClient, anna: User) -> None:
    response = await client.post("/auth/login", json={"email": "Anna@Example.com"})

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("pc_session=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie
    body = response.json()
    assert body["user"]["id"] == str(anna.id)
    assert [(m["team"]["slug"], m["role"]) for m in body["memberships"]] == [("payments", "lead")]


async def test_only_the_token_hash_is_stored(client: AsyncClient, session: AsyncSession, anna: User) -> None:
    await client.post("/auth/login", json={"email": anna.email})
    token = client.cookies["pc_session"]

    stored = await session.scalar(select(UserSession).where(UserSession.user_id == anna.id))

    assert stored is not None
    assert stored.token_hash != token.encode()
    assert len(stored.token_hash) == 32


async def test_login_with_an_unknown_email_is_not_found(client: AsyncClient) -> None:
    response = await client.post("/auth/login", json={"email": "nobody@example.com"})

    assert response.status_code == 404
    assert "set-cookie" not in response.headers


async def test_soft_deleted_user_cannot_log_in(client: AsyncClient, session: AsyncSession, anna: User) -> None:
    anna.deleted_at = datetime.now(UTC)
    await session.flush()

    response = await client.post("/auth/login", json={"email": anna.email})

    assert response.status_code == 404


async def test_login_picks_the_active_user_when_a_deleted_one_had_the_email(
    client: AsyncClient, session: AsyncSession
) -> None:
    former = User(email="anna@example.com", display_name="Former", timezone="UTC", role=GlobalRole.USER)
    session.add(former)
    await session.flush()
    former.deleted_at = datetime.now(UTC)
    await session.flush()
    current = User(email="anna@example.com", display_name="Current", timezone="UTC", role=GlobalRole.USER)
    session.add(current)
    await session.flush()

    response = await client.post("/auth/login", json={"email": "anna@example.com"})

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(current.id)


async def test_me_returns_the_logged_in_user(client: AsyncClient, anna: User) -> None:
    await client.post("/auth/login", json={"email": anna.email})

    response = await client.get("/me")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "anna@example.com"


@pytest.mark.parametrize("cookie", [None, "", "not-a-session"])
async def test_missing_or_unknown_cookie_is_unauthenticated(client: AsyncClient, cookie: str | None) -> None:
    if cookie is not None:
        client.cookies.set("pc_session", cookie)

    response = await client.get("/me")

    assert response.status_code == 401


async def test_expired_session_is_unauthenticated(client: AsyncClient, anna: User) -> None:
    await client.post("/auth/login", json={"email": anna.email})

    with time_machine.travel(datetime.now(UTC) + timedelta(hours=12, seconds=1)):
        response = await client.get("/me")

    assert response.status_code == 401


async def test_routers_behind_authenticated_reject_anonymous_requests(client: AsyncClient) -> None:
    response = await client.get("/users")

    assert response.status_code == 401


async def test_logout_deletes_the_session_and_clears_the_cookie(
    client: AsyncClient, session: AsyncSession, anna: User
) -> None:
    await client.post("/auth/login", json={"email": anna.email})
    token = client.cookies["pc_session"]

    response = await client.post("/auth/logout")

    assert response.status_code == 204
    assert 'pc_session=""' in response.headers["set-cookie"]
    assert await session.scalar(select(func.count()).select_from(UserSession)) == 0
    client.cookies.set("pc_session", token)
    assert (await client.get("/me")).status_code == 401
