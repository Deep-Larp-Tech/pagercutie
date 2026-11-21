import asyncio
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import anyio
import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.alerts.models import Alert
from pagercutie.alerts.schemas import AlertStatus
from pagercutie.alerts.service import AlertChanged, feed_events
from pagercutie.auth.models import UserSession
from pagercutie.auth.service import CurrentUser
from pagercutie.core.broadcast import Broadcast, Subscription
from pagercutie.core.db import get_session, get_sessionmaker
from pagercutie.core.deps import get_alert_changes
from pagercutie.core.enums import Severity
from pagercutie.core.settings import Settings
from pagercutie.main import create_app
from pagercutie.rules.ast import Compare
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, UserRecipient
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole
from sse import parse_sse

pytestmark = pytest.mark.anyio


class WatchedBroadcast(Broadcast):
    """Signals each new subscription, so a test publishes only once the stream listens."""

    def __init__(self) -> None:
        super().__init__()
        self.subscribed = asyncio.Event()

    @asynccontextmanager
    async def subscribe(self) -> AsyncGenerator[Subscription]:
        async with super().subscribe() as subscription:
            self.subscribed.set()
            yield subscription


@dataclass
class World:
    team: Team
    member: User
    outsider: User
    alert: Alert


async def _user(session: AsyncSession, name: str) -> User:
    user = User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=GlobalRole.USER)
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def world(session: AsyncSession) -> World:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    member = await _user(session, "member")
    outsider = await _user(session, "outsider")
    session.add(Membership(team_id=team.id, user_id=member.id, role=TeamRole.MEMBER))
    rule = Rule(
        name="Payment failed",
        enabled=True,
        team_id=team.id,
        user_id=None,
        schema_ids=[],
        condition=Compare(op="eq", field="payload.type", value="failed"),
        dedup=Dedup(fields=[]),
        routing=Routing(recipients=[UserRecipient(type="user", user_id=member.id)]),
        presentation=Presentation(title="Failed", severity=Severity.ERROR, colour=Colour.RED),
    )
    session.add(rule)
    await session.flush()
    now = datetime.now(UTC)
    alert = Alert(
        rule_id=rule.id,
        team_id=team.id,
        fingerprint="f" * 64,
        status=AlertStatus.OPEN,
        severity=Severity.ERROR,
        colour=Colour.RED,
        title="Failed",
        fields=[],
        occurrences=1,
        first_seen_at=now,
        last_seen_at=now,
        notified_at=now,
        escalated_team_ids=[],
        payload={},
    )
    session.add(alert)
    await session.flush()
    return World(team=team, member=member, outsider=outsider, alert=alert)


@pytest.fixture
def app(settings: Settings, session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = create_app(settings)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_sessionmaker] = lambda: sessionmaker
    return app


@pytest.fixture
def alert_changes(app: FastAPI) -> WatchedBroadcast:
    broadcast = WatchedBroadcast()
    app.dependency_overrides[get_alert_changes] = lambda: broadcast
    broadcast.open()
    return broadcast


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def login(client: AsyncClient, user: User) -> None:
    response = await client.post("/auth/login", json={"email": user.email})
    assert response.status_code == 200


async def open_stream(client: AsyncClient, alert_changes: WatchedBroadcast) -> asyncio.Task[httpx.Response]:
    """Starts GET /alerts/stream and returns once it has subscribed. ASGITransport answers only after the stream
    ends, so each test ends it (close or a bad payload) before awaiting the response."""
    alert_changes.subscribed.clear()
    stream = asyncio.create_task(client.get("/alerts/stream"))
    with anyio.fail_after(5):
        await alert_changes.subscribed.wait()
    return stream


def changed(alert: Alert) -> str:
    return AlertChanged(type="alert.updated", alert_id=alert.id).model_dump_json()


async def test_stream_without_a_session_answers_401_json(client: AsyncClient) -> None:
    response = await client.get("/alerts/stream")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/json"


async def test_member_receives_an_acknowledged_alert(
    client: AsyncClient, alert_changes: WatchedBroadcast, world: World
) -> None:
    await login(client, world.member)
    assert (await client.post(f"/alerts/{world.alert.id}/acknowledge")).status_code == 200
    stream = await open_stream(client, alert_changes)

    alert_changes.publish(changed(world.alert))
    alert_changes.close()
    response = await stream

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert [(e["type"], e["alert"]["id"], e["alert"]["status"]) for e in events] == [
        ("alert.updated", str(world.alert.id), "acknowledged")
    ]


async def test_outsider_does_not_receive_the_teams_alert(
    client: AsyncClient, alert_changes: WatchedBroadcast, world: World
) -> None:
    await login(client, world.outsider)
    stream = await open_stream(client, alert_changes)

    alert_changes.publish(changed(world.alert))
    alert_changes.close()
    response = await stream

    assert response.status_code == 200
    assert parse_sse(response.text) == []


async def test_an_empty_payload_ends_the_stream(
    client: AsyncClient, alert_changes: WatchedBroadcast, world: World
) -> None:
    await login(client, world.member)
    stream = await open_stream(client, alert_changes)

    alert_changes.publish("")
    with anyio.fail_after(5):
        response = await stream

    assert parse_sse(response.text) == []
    assert alert_changes.subscriber_count == 0


async def test_a_revoked_session_ends_the_stream_on_the_next_change(
    client: AsyncClient, session: AsyncSession, alert_changes: WatchedBroadcast, world: World
) -> None:
    await login(client, world.member)
    stream = await open_stream(client, alert_changes)
    await session.execute(delete(UserSession).where(UserSession.user_id == world.member.id))

    alert_changes.publish(changed(world.alert))
    with anyio.fail_after(5):
        response = await stream

    assert parse_sse(response.text) == []


async def test_stream_ends_at_once_while_nothing_listens(client: AsyncClient, world: World) -> None:
    await login(client, world.member)

    with anyio.fail_after(5):
        response = await client.get("/alerts/stream")

    assert response.status_code == 200
    assert parse_sse(response.text) == []


async def test_created_wins_within_a_batch_and_team_id_filters(session: AsyncSession, world: World) -> None:
    member = CurrentUser(
        id=world.member.id, role=GlobalRole.USER, session_token_hash=b"", team_roles={world.team.id: TeamRole.MEMBER}
    )
    batch = [changed(world.alert), AlertChanged(type="alert.created", alert_id=world.alert.id).model_dump_json()]

    merged = await feed_events(session, member, batch, None)
    other_team = await feed_events(session, member, batch, uuid.uuid4())

    assert [(e.type, e.alert.id) for e in merged] == [("alert.created", world.alert.id)]
    assert other_team == []
