import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, Delivery
from pagercutie.alerts.schemas import AlertStatus, DeliveryStatus
from pagercutie.core.enums import Channel, Severity
from pagercutie.rules.ast import Compare
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, UserRecipient
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

NOW = datetime.now(UTC)


@dataclass
class World:
    """Alerts owned by team A, team B and Anna's personal rule; team B's alert is also escalated to team C."""

    admin: User
    anna: User  # viewer of team A, owns the personal rule
    bob: User  # member of team B
    carol: User  # lead of team C
    dave: User  # in no team
    team_alert: Alert
    other_team_alert: Alert
    personal_alert: Alert


async def _user(session: AsyncSession, name: str, role: GlobalRole = GlobalRole.USER) -> User:
    user = User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=role)
    session.add(user)
    await session.flush()
    return user


async def _team(session: AsyncSession, slug: str, member: User, role: TeamRole) -> Team:
    team = Team(slug=slug, name=slug)
    session.add(team)
    await session.flush()
    session.add(Membership(team_id=team.id, user_id=member.id, role=role))
    await session.flush()
    return team


async def _rule(session: AsyncSession, *, team_id: uuid.UUID | None, user_id: uuid.UUID | None) -> Rule:
    rule = Rule(
        name="Rule",
        enabled=True,
        team_id=team_id,
        user_id=user_id,
        schema_ids=[],
        condition=Compare(op="eq", field="payload.type", value="failed"),
        dedup=Dedup(fields=[]),
        routing=Routing(recipients=[UserRecipient(type="user", user_id=uuid.uuid4())]),
        presentation=Presentation(title="Failed", severity=Severity.ERROR, colour=Colour.RED),
    )
    session.add(rule)
    await session.flush()
    return rule


async def _alert(session: AsyncSession, rule: Rule, escalated_team_ids: list[uuid.UUID] | None = None) -> Alert:
    alert = Alert(
        rule_id=rule.id,
        team_id=rule.team_id,
        fingerprint=uuid.uuid4().hex + uuid.uuid4().hex,
        status=AlertStatus.OPEN,
        severity=Severity.ERROR,
        colour=Colour.RED,
        title="Failed",
        fields=[],
        occurrences=1,
        notified_at=NOW,
        first_seen_at=NOW,
        last_seen_at=NOW,
        escalated_team_ids=escalated_team_ids or [],
        payload={},
    )
    session.add(alert)
    await session.flush()
    return alert


async def _delivery(
    session: AsyncSession,
    alert: Alert,
    user: User,
    message: str,
    *,
    age_minutes: int = 0,
    channel: Channel = Channel.EMAIL,
    status: DeliveryStatus = DeliveryStatus.SENT,
) -> Delivery:
    delivery = Delivery(
        id=uuid.uuid7(),
        alert_id=alert.id,
        user_id=user.id,
        channel=channel,
        status=status,
        message=message,
        received_at=NOW - timedelta(minutes=age_minutes),
    )
    session.add(delivery)
    await session.flush()
    # created_at is the transaction time, which every row of a test shares.
    await session.execute(
        update(Delivery).where(Delivery.id == delivery.id).values(created_at=NOW - timedelta(minutes=age_minutes))
    )
    return delivery


async def _login(client: AsyncClient, user: User) -> None:
    assert (await client.post("/auth/login", json={"email": user.email})).status_code == 200


@pytest.fixture
async def world(session: AsyncSession) -> World:
    admin = await _user(session, "admin", GlobalRole.ADMIN)
    anna = await _user(session, "anna")
    bob = await _user(session, "bob")
    carol = await _user(session, "carol")
    dave = await _user(session, "dave")
    team_a = await _team(session, "team-a", anna, TeamRole.VIEWER)
    team_b = await _team(session, "team-b", bob, TeamRole.MEMBER)
    team_c = await _team(session, "team-c", carol, TeamRole.LEAD)
    team_alert = await _alert(session, await _rule(session, team_id=team_a.id, user_id=None))
    other_team_alert = await _alert(
        session, await _rule(session, team_id=team_b.id, user_id=None), escalated_team_ids=[team_c.id]
    )
    personal_alert = await _alert(session, await _rule(session, team_id=None, user_id=anna.id))
    await _delivery(session, team_alert, anna, "team A", age_minutes=3)
    await _delivery(session, other_team_alert, bob, "team B", age_minutes=2)
    await _delivery(session, personal_alert, anna, "personal", age_minutes=1)
    return World(admin, anna, bob, carol, dave, team_alert, other_team_alert, personal_alert)


async def _messages(client: AsyncClient, user: User, **params: str | int | list[str]) -> list[str]:
    await _login(client, user)
    response = await client.get("/deliveries", params=params)
    assert response.status_code == 200
    return [d["message"] for d in response.json()]


async def test_deliveries_require_authentication(client: AsyncClient, world: World) -> None:
    assert (await client.get("/deliveries")).status_code == 401
    assert (await client.get(f"/alerts/{world.team_alert.id}/deliveries")).status_code == 401


async def test_members_see_deliveries_of_their_teams_and_personal_rules(client: AsyncClient, world: World) -> None:
    # A viewer sees every delivery of the team's alert, not only their own.
    assert await _messages(client, world.anna) == ["personal", "team A"]
    assert await _messages(client, world.bob) == ["team B"]


async def test_escalated_alerts_are_visible_to_the_escalated_team(client: AsyncClient, world: World) -> None:
    assert await _messages(client, world.carol) == ["team B"]


async def test_users_outside_every_team_see_nothing(client: AsyncClient, world: World) -> None:
    assert await _messages(client, world.dave) == []


async def test_admins_see_all_deliveries_newest_first(client: AsyncClient, world: World) -> None:
    assert await _messages(client, world.admin) == ["personal", "team B", "team A"]


async def test_personal_rule_alerts_are_visible_to_their_owner_only(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await _delivery(session, world.personal_alert, world.bob, "to bob", age_minutes=0)

    assert "personal" in await _messages(client, world.anna)
    assert "personal" not in await _messages(client, world.bob)
    assert "to bob" not in await _messages(client, world.bob)
    assert "personal" not in await _messages(client, world.carol)


async def test_filters_by_channel_and_status(client: AsyncClient, session: AsyncSession, world: World) -> None:
    await _delivery(
        session, world.team_alert, world.anna, "sms failed", channel=Channel.SMS, status=DeliveryStatus.FAILED
    )
    await _delivery(session, world.team_alert, world.anna, "phone sent", channel=Channel.PHONE)

    assert await _messages(client, world.anna, channel="sms") == ["sms failed"]
    assert await _messages(client, world.anna, channel=["sms", "phone"]) == ["phone sent", "sms failed"]
    assert await _messages(client, world.anna, status="failed") == ["sms failed"]
    assert await _messages(client, world.anna, channel="phone", status="failed") == []
    assert await _messages(client, world.anna, status=["failed", "sent"]) == [
        "phone sent",
        "sms failed",
        "personal",
        "team A",
    ]


async def test_pagination_walks_newest_first(client: AsyncClient, world: World) -> None:
    assert await _messages(client, world.admin, limit=2) == ["personal", "team B"]
    assert await _messages(client, world.admin, limit=2, offset=2) == ["team A"]
    assert await _messages(client, world.admin, limit=2, offset=3) == []


async def test_equal_timestamps_are_ordered_by_id_descending(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    for name in ("first", "second", "third"):
        await _delivery(session, world.team_alert, world.anna, name, age_minutes=0)

    assert (await _messages(client, world.anna))[:3] == ["third", "second", "first"]


async def test_invalid_query_parameters_are_rejected(client: AsyncClient, world: World) -> None:
    await _login(client, world.admin)

    assert (await client.get("/deliveries", params={"channel": "pigeon"})).status_code == 422
    assert (await client.get("/deliveries", params={"status": "lost"})).status_code == 422
    assert (await client.get("/deliveries", params={"limit": 0})).status_code == 422


async def test_alert_deliveries_are_listed_newest_first(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await _delivery(session, world.team_alert, world.anna, "newer", age_minutes=0, channel=Channel.SMS)
    await _login(client, world.anna)

    response = await client.get(f"/alerts/{world.team_alert.id}/deliveries")

    assert response.status_code == 200
    assert [d["message"] for d in response.json()] == ["newer", "team A"]
    assert {d["alert_id"] for d in response.json()} == {str(world.team_alert.id)}


async def test_alert_deliveries_follow_alert_visibility(client: AsyncClient, world: World) -> None:
    own = f"/alerts/{world.other_team_alert.id}/deliveries"

    await _login(client, world.bob)
    assert (await client.get(own)).status_code == 200
    # Escalated to team C.
    await _login(client, world.carol)
    assert (await client.get(own)).status_code == 200
    await _login(client, world.admin)
    assert (await client.get(own)).status_code == 200
    # Anna is in team A only; the answer is the same as for a missing alert.
    await _login(client, world.anna)
    assert (await client.get(own)).status_code == 404
    await _login(client, world.dave)
    assert (await client.get(own)).status_code == 404


async def test_personal_alert_deliveries_are_visible_to_the_owner_only(client: AsyncClient, world: World) -> None:
    url = f"/alerts/{world.personal_alert.id}/deliveries"

    await _login(client, world.anna)
    assert [d["message"] for d in (await client.get(url)).json()] == ["personal"]
    for user in (world.bob, world.carol, world.dave):
        await _login(client, user)
        assert (await client.get(url)).status_code == 404
    await _login(client, world.admin)
    assert (await client.get(url)).status_code == 200


async def test_missing_alert_deliveries_are_not_found(client: AsyncClient, world: World) -> None:
    await _login(client, world.admin)

    assert (await client.get(f"/alerts/{uuid.uuid4()}/deliveries")).status_code == 404
