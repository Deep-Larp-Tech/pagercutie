import asyncio
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, time, timedelta

import anyio
import asyncpg
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from pagercutie.alerts.models import Alert, Delivery
from pagercutie.alerts.schemas import AlertStatus, DeliveryStatus
from pagercutie.core.db import NotifyChannel
from pagercutie.core.enums import Channel, Severity, Weekday
from pagercutie.core.templates import render_message
from pagercutie.pipeline.messages import Event, Match, Opened, Renotified
from pagercutie.pipeline.routing.stage import route
from pagercutie.preferences.schemas import ChannelPreferences, ChannelRule, TimeWindow
from pagercutie.rules.ast import Compare
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, RuleRead, UserRecipient
from pagercutie.teams.models import Membership, Rotation, RotationMember, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

# A Saturday; Europe/Prague is on CET (UTC+1) and the Settlements rotation hands off on Mondays.
NOON = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
TITLE = "Settlement failed"
BODY = "Workflow wf-1 failed"

ANNA_PREFERENCES = ChannelPreferences(
    rules=[
        ChannelRule(
            min_severity=Severity.CRITICAL,
            channels=[Channel.SMS],
            window=TimeWindow(days=list(Weekday), start=time(8), end=time(20)),
        ),
        ChannelRule(min_severity=Severity.CRITICAL, channels=[Channel.EMAIL]),
    ]
)


def preferences(*channels: Channel, min_severity: Severity = Severity.CRITICAL) -> ChannelPreferences:
    return ChannelPreferences(rules=[ChannelRule(min_severity=min_severity, channels=list(channels))])


async def make_user(
    session: AsyncSession,
    name: str,
    *,
    timezone: str = "Europe/Prague",
    prefs: ChannelPreferences | None = None,
    deleted: bool = False,
) -> User:
    user = User(
        email=f"{name}-{uuid.uuid4().hex[:8]}@example.com",
        display_name=name,
        timezone=timezone,
        role=GlobalRole.USER,
        channel_preferences=prefs or ChannelPreferences(),
        deleted_at=NOON if deleted else None,
    )
    session.add(user)
    await session.flush()
    return user


async def make_team(session: AsyncSession, prefs: ChannelPreferences | None = None) -> Team:
    team = Team(
        slug=f"team-{uuid.uuid4().hex[:8]}", name="Settlements", channel_preferences=prefs or ChannelPreferences()
    )
    session.add(team)
    await session.flush()
    return team


async def add_members(session: AsyncSession, team: Team, members: Mapping[User, TeamRole]) -> None:
    session.add_all(Membership(team_id=team.id, user_id=user.id, role=role) for user, role in members.items())
    await session.flush()


async def make_rotation(session: AsyncSession, team: Team, *users: User) -> None:
    rotation = Rotation(
        team_id=team.id,
        handoff_day=Weekday.MON,
        handoff_time=time(9),
        timezone="Europe/Prague",
        members=[RotationMember(position=position, user_id=user.id) for position, user in enumerate(users)],
    )
    rotation.started_at = datetime(2026, 11, 1, tzinfo=UTC)
    session.add(rotation)
    await session.flush()


async def make_alert(session: AsyncSession, team: Team, severity: Severity = Severity.CRITICAL) -> Alert:
    rule = Rule(
        name="Settlement failed",
        enabled=True,
        team_id=team.id,
        user_id=None,
        schema_ids=[],
        condition=Compare(op="eq", field="payload.type", value="failed"),
        dedup=Dedup(fields=[]),
        routing=Routing(recipients=[UserRecipient(type="user", user_id=uuid.uuid4())]),
        presentation=Presentation(title=TITLE, severity=severity, colour=Colour.RED),
    )
    session.add(rule)
    await session.flush()
    alert = Alert(
        rule_id=rule.id,
        team_id=team.id,
        fingerprint=uuid.uuid4().hex + uuid.uuid4().hex,
        status=AlertStatus.OPEN,
        severity=severity,
        colour=Colour.RED,
        title=TITLE,
        body=BODY,
        fields=[],
        occurrences=1,
        notified_at=NOON,
        first_seen_at=NOON,
        last_seen_at=NOON,
        escalated_team_ids=[],
        payload={},
    )
    session.add(alert)
    await session.flush()
    return alert


def match_for(
    alert: Alert,
    recipients: list[dict[str, str]],
    *,
    channels: list[Channel] | None = None,
    received_at: datetime = NOON,
) -> Match:
    assert alert.team_id is not None
    rule = RuleRead.model_validate(
        {
            "id": alert.rule_id,
            "name": "Settlement failed",
            "description": None,
            "enabled": True,
            "owner": {"type": "team", "team_id": alert.team_id},
            "schema_ids": [],
            "condition": {"op": "exists", "field": "payload.workflowId"},
            "dedup": {"fields": []},
            "routing": {"recipients": recipients, "channels": channels},
            "presentation": {"title": TITLE, "severity": alert.severity, "colour": "red"},
            "runbook_id": None,
            "created_at": NOON,
            "updated_at": NOON,
        }
    )
    event = Event(
        event_id=uuid.uuid7(),
        source="payments-webhook",
        source_id=uuid.uuid7(),
        team_id=alert.team_id,
        schema_id=uuid.uuid7(),
        schema_name="payment",
        severity=alert.severity,
        received_at=received_at,
        payload={"workflowId": "wf-1"},
    )
    return Match(event=event, rule=rule, fingerprint=alert.fingerprint)


def opened(
    alert: Alert,
    recipients: list[dict[str, str]],
    *,
    channels: list[Channel] | None = None,
    received_at: datetime = NOON,
) -> Opened:
    return Opened(alert_id=alert.id, match=match_for(alert, recipients, channels=channels, received_at=received_at))


def user_recipient(user: User) -> dict[str, str]:
    return {"type": "user", "user_id": str(user.id)}


def team_recipient(team: Team) -> dict[str, str]:
    return {"type": "team", "team_id": str(team.id)}


def on_call_recipient(team: Team) -> dict[str, str]:
    return {"type": "on_call", "team_id": str(team.id)}


async def delivered(session: AsyncSession, alert: Alert) -> dict[uuid.UUID, set[Channel]]:
    """Channels of the alert's deliveries, by user."""
    rows = await session.execute(select(Delivery.user_id, Delivery.channel).where(Delivery.alert_id == alert.id))
    result: dict[uuid.UUID, set[Channel]] = {}
    for user_id, channel in rows:
        result.setdefault(user_id, set()).add(channel)
    return result


async def delivery_count(session: AsyncSession, alert: Alert) -> int:
    count = await session.scalar(select(func.count()).select_from(Delivery).where(Delivery.alert_id == alert.id))
    assert count is not None
    return count


async def test_a_user_recipient_gets_the_channels_of_their_own_preferences_and_the_ui(session: AsyncSession) -> None:
    team = await make_team(session, preferences(Channel.PHONE))
    boris = await make_user(session, "boris", prefs=preferences(Channel.SMS))
    alert = await make_alert(session, team)

    ids = await route(session, opened(alert, [user_recipient(boris)]))

    assert await delivered(session, alert) == {boris.id: {Channel.SMS, Channel.UI}}
    assert len(ids) == 2
    rows = (await session.scalars(select(Delivery).where(Delivery.alert_id == alert.id))).all()
    assert {row.id for row in rows} == set(ids)
    assert {row.status for row in rows} == {DeliveryStatus.PENDING}
    assert {row.attempts for row in rows} == {0}
    assert {row.received_at for row in rows} == {NOON}
    assert {row.channel: row.message for row in rows} == {
        channel: render_message(channel, TITLE, BODY) for channel in (Channel.SMS, Channel.UI)
    }


async def test_deliveries_take_received_at_from_the_event(session: AsyncSession) -> None:
    team = await make_team(session)
    boris = await make_user(session, "boris", prefs=preferences(Channel.SMS))
    alert = await make_alert(session, team)
    received_at = NOON + timedelta(minutes=17)

    await route(session, opened(alert, [user_recipient(boris)], received_at=received_at))

    rows = (await session.scalars(select(Delivery).where(Delivery.alert_id == alert.id))).all()
    assert {row.received_at for row in rows} == {received_at}


async def test_a_team_recipient_reaches_leads_and_members_with_the_team_preferences(session: AsyncSession) -> None:
    team = await make_team(session, preferences(Channel.EMAIL))
    lead = await make_user(session, "lead", prefs=preferences(Channel.PHONE))
    member = await make_user(session, "member")
    viewer = await make_user(session, "viewer")
    await add_members(session, team, {lead: TeamRole.LEAD, member: TeamRole.MEMBER, viewer: TeamRole.VIEWER})
    alert = await make_alert(session, team)

    await route(session, opened(alert, [team_recipient(team)]))

    assert await delivered(session, alert) == {
        lead.id: {Channel.EMAIL, Channel.UI},
        member.id: {Channel.EMAIL, Channel.UI},
    }


async def test_an_on_call_recipient_reaches_only_the_user_on_call_at_the_event_time(session: AsyncSession) -> None:
    team = await make_team(session, preferences(Channel.EMAIL))
    boris = await make_user(session, "boris")
    carla = await make_user(session, "carla")
    await make_rotation(session, team, boris, carla)
    alert = await make_alert(session, team)

    await route(session, opened(alert, [on_call_recipient(team)]))

    assert await delivered(session, alert) == {carla.id: {Channel.EMAIL, Channel.UI}}


async def test_routing_channels_override_the_preferences(session: AsyncSession) -> None:
    team = await make_team(session)
    boris = await make_user(session, "boris", prefs=preferences(Channel.SMS))
    alert = await make_alert(session, team)

    await route(session, opened(alert, [user_recipient(boris)], channels=[Channel.PHONE]))

    assert await delivered(session, alert) == {boris.id: {Channel.PHONE, Channel.UI}}


@pytest.mark.parametrize(
    ("received_at", "expected"),
    [
        pytest.param(datetime(2026, 11, 21, 6, 59, tzinfo=UTC), Channel.EMAIL, id="07:59 local"),
        pytest.param(datetime(2026, 11, 21, 7, 0, tzinfo=UTC), Channel.SMS, id="08:00 local"),
        pytest.param(datetime(2026, 11, 21, 18, 59, tzinfo=UTC), Channel.SMS, id="19:59 local"),
        pytest.param(datetime(2026, 11, 21, 19, 0, tzinfo=UTC), Channel.EMAIL, id="20:00 local"),
    ],
)
async def test_annas_sms_window_is_evaluated_in_her_time_zone(
    session: AsyncSession, received_at: datetime, expected: Channel
) -> None:
    team = await make_team(session)
    anna = await make_user(session, "anna", timezone="Europe/Prague", prefs=ANNA_PREFERENCES)
    alert = await make_alert(session, team)

    await route(session, opened(alert, [user_recipient(anna)], received_at=received_at))

    assert await delivered(session, alert) == {anna.id: {expected, Channel.UI}}


@pytest.mark.parametrize("override", [None, [Channel.PHONE, Channel.SMS]], ids=["team preferences", "rule channels"])
async def test_the_settlements_on_call_user_gets_phone_sms_and_the_ui(
    session: AsyncSession, override: list[Channel] | None
) -> None:
    team = await make_team(session, preferences(Channel.PHONE, Channel.SMS))
    boris = await make_user(session, "boris")
    carla = await make_user(session, "carla")
    await make_rotation(session, team, boris, carla)
    alert = await make_alert(session, team)

    await route(session, opened(alert, [on_call_recipient(team)], channels=override))

    assert await delivered(session, alert) == {carla.id: {Channel.PHONE, Channel.SMS, Channel.UI}}


async def test_routing_the_same_outcome_twice_inserts_nothing_the_second_time(session: AsyncSession) -> None:
    team = await make_team(session, preferences(Channel.EMAIL))
    boris = await make_user(session, "boris")
    await add_members(session, team, {boris: TeamRole.MEMBER})
    alert = await make_alert(session, team)
    outcome = opened(alert, [team_recipient(team)])

    first = await route(session, outcome)
    second = await route(session, outcome)

    assert len(first) == 2
    assert second == []
    assert await delivery_count(session, alert) == 2


async def test_a_renotification_inserts_a_second_set_and_repeats_inserts_nothing(session: AsyncSession) -> None:
    team = await make_team(session, preferences(Channel.EMAIL))
    boris = await make_user(session, "boris")
    await add_members(session, team, {boris: TeamRole.MEMBER})
    alert = await make_alert(session, team)
    recipients = [team_recipient(team)]
    renotified = Renotified(alert_id=alert.id, match=match_for(alert, recipients), notification_seq=2)

    first = await route(session, opened(alert, recipients))
    second = await route(session, renotified)
    again = await route(session, renotified)

    assert len(first) == len(second) == 2
    assert set(first).isdisjoint(second)
    assert again == []
    assert await delivery_count(session, alert) == 4


async def test_soft_deleted_users_are_skipped_with_a_warning(session: AsyncSession) -> None:
    team = await make_team(session, preferences(Channel.EMAIL))
    gone = await make_user(session, "gone", deleted=True)
    boris = await make_user(session, "boris")
    await add_members(session, team, {gone: TeamRole.LEAD, boris: TeamRole.MEMBER})
    alert = await make_alert(session, team)

    with capture_logs() as logs:
        ids = await route(session, opened(alert, [user_recipient(gone), team_recipient(team)]))

    assert await delivered(session, alert) == {boris.id: {Channel.EMAIL, Channel.UI}}
    assert len(ids) == 2
    skipped = [entry for entry in logs if entry["event"] == "routing.skipped"]
    assert [(entry["log_level"], entry["reason"], entry["user_id"]) for entry in skipped] == [
        ("warning", "user_deleted", gone.id),
        ("warning", "user_deleted", gone.id),
    ]


async def test_a_user_reached_by_several_recipients_gets_one_delivery_per_channel(session: AsyncSession) -> None:
    team = await make_team(session, preferences(Channel.EMAIL))
    boris = await make_user(session, "boris", prefs=preferences(Channel.SMS, Channel.EMAIL))
    await add_members(session, team, {boris: TeamRole.MEMBER})
    alert = await make_alert(session, team)

    ids = await route(session, opened(alert, [user_recipient(boris), team_recipient(team)]))

    assert await delivered(session, alert) == {boris.id: {Channel.SMS, Channel.EMAIL, Channel.UI}}
    assert len(ids) == len(set(ids)) == 3
    assert await delivery_count(session, alert) == 3


async def test_an_on_call_recipient_without_a_rotation_or_members_is_skipped_with_a_warning(
    session: AsyncSession,
) -> None:
    team = await make_team(session, preferences(Channel.EMAIL))
    empty = await make_team(session, preferences(Channel.EMAIL))
    await make_rotation(session, empty)
    alert = await make_alert(session, team)

    with capture_logs() as logs:
        ids = await route(session, opened(alert, [on_call_recipient(team), on_call_recipient(empty)]))

    assert ids == []
    assert await delivery_count(session, alert) == 0
    assert [(entry["log_level"], entry["reason"]) for entry in logs if entry["event"] == "routing.skipped"] == [
        ("warning", "no_rotation"),
        ("warning", "rotation_without_members"),
    ]


async def test_a_severity_below_every_preference_rule_gets_only_the_ui(session: AsyncSession) -> None:
    team = await make_team(session)
    boris = await make_user(session, "boris", prefs=preferences(Channel.SMS, min_severity=Severity.CRITICAL))
    alert = await make_alert(session, team, severity=Severity.WARN)

    await route(session, opened(alert, [user_recipient(boris)]))

    assert await delivered(session, alert) == {boris.id: {Channel.UI}}


class Listener:
    """A separate connection that LISTENs on `deliveries_pending`, so only committed notifications reach it."""

    def __init__(self, notifications: asyncio.Queue[str]) -> None:
        self.notifications = notifications

    async def next(self) -> str:
        with anyio.fail_after(5):
            return await self.notifications.get()


@pytest.fixture
async def listener(engine: AsyncEngine) -> AsyncIterator[Listener]:
    notifications: asyncio.Queue[str] = asyncio.Queue()

    def on_notification(_connection: object, _pid: int, _channel: str, payload: str) -> None:
        notifications.put_nowait(payload)

    async with engine.connect() as connection:
        driver = (await connection.get_raw_connection()).driver_connection
        if not isinstance(driver, asyncpg.Connection):
            raise TypeError(f"LISTEN needs an asyncpg connection, the engine gave {type(driver).__name__}")
        await driver.add_listener(NotifyChannel.DELIVERIES_PENDING, on_notification)
        try:
            yield Listener(notifications)
        finally:
            await connection.invalidate()


async def send_sentinel(engine: AsyncEngine) -> None:
    """Notifications arrive in commit order, so once the sentinel is seen everything sent before it has been."""
    async with engine.begin() as connection:
        await connection.execute(select(func.pg_notify(NotifyChannel.DELIVERIES_PENDING, "sentinel")))


async def test_the_notification_is_sent_when_the_transaction_commits(engine: AsyncEngine, listener: Listener) -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session, session.begin():
        team = await make_team(session)
        boris = await make_user(session, "boris", prefs=preferences(Channel.EMAIL))
        alert = await make_alert(session, team)
        outcome = opened(alert, [user_recipient(boris)])
        ids = await route(session, outcome)
        # A second call inserts nothing and must not notify again.
        assert await route(session, outcome) == []
    try:
        assert len(ids) == 2
        await send_sentinel(engine)
        assert [await listener.next(), await listener.next()] == ["", "sentinel"]
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(Delivery).where(Delivery.alert_id == alert.id))
            await connection.execute(delete(Alert).where(Alert.id == alert.id))
            await connection.execute(delete(Rule).where(Rule.id == alert.rule_id))
            await connection.execute(delete(Team).where(Team.id == team.id))
            await connection.execute(delete(User).where(User.id == boris.id))


async def test_a_rolled_back_transaction_sends_no_notification(engine: AsyncEngine, listener: Listener) -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    with pytest.raises(RuntimeError, match="abort"):
        async with sessionmaker() as session, session.begin():
            team = await make_team(session)
            boris = await make_user(session, "boris", prefs=preferences(Channel.EMAIL))
            alert = await make_alert(session, team)
            assert len(await route(session, opened(alert, [user_recipient(boris)]))) == 2
            raise RuntimeError("abort")

    await send_sentinel(engine)

    assert await listener.next() == "sentinel"
