import uuid
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, Delivery
from pagercutie.alerts.schemas import AlertStatus, DeliveryStatus
from pagercutie.auth.models import UserSession
from pagercutie.core.enums import Channel, Severity
from pagercutie.rules.ast import Compare
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, UserRecipient
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


async def test_messages_lists_own_deliveries_newest_first_filtered_by_channel(
    client: AsyncClient, session: AsyncSession, anna: User
) -> None:
    other = User(email="bob@example.com", display_name="Bob", timezone="UTC", role=GlobalRole.USER)
    session.add(other)
    await session.flush()
    rule = Rule(
        name="Workflow failed",
        enabled=True,
        user_id=anna.id,
        schema_ids=[],
        condition=Compare(op="eq", field="payload.type", value="failed"),
        dedup=Dedup(fields=[]),
        routing=Routing(recipients=[UserRecipient(type="user", user_id=anna.id)]),
        presentation=Presentation(title="Failed", severity=Severity.ERROR),
    )
    session.add(rule)
    await session.flush()
    now = datetime.now(UTC)
    alert = Alert(
        rule_id=rule.id,
        fingerprint="f" * 64,
        status=AlertStatus.OPEN,
        severity=Severity.ERROR,
        colour=Colour.RED,
        title="Failed",
        fields=[],
        occurrences=1,
        first_seen_at=now,
        last_seen_at=now,
        escalated_team_ids=[],
        payload={},
    )
    session.add(alert)
    await session.flush()

    def delivery(user: User, channel: Channel, message: str) -> Delivery:
        return Delivery(
            id=uuid.uuid7(),
            alert_id=alert.id,
            user_id=user.id,
            channel=channel,
            status=DeliveryStatus.SENT,
            message=message,
        )

    for d in [
        delivery(anna, Channel.SMS, "first"),
        delivery(anna, Channel.EMAIL, "email"),
        delivery(anna, Channel.PHONE, "second"),
        delivery(other, Channel.SMS, "bob's"),
    ]:
        session.add(d)
        await session.flush()
    await client.post("/auth/login", json={"email": anna.email})

    response = await client.get("/me/messages", params={"channel": ["sms", "phone"]})

    assert response.status_code == 200
    assert [m["message"] for m in response.json()] == ["second", "first"]
