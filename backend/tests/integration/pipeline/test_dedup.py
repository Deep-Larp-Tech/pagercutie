import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pagercutie.alerts.models import Alert
from pagercutie.alerts.schemas import AlertField, AlertStatus, Resolution
from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction
from pagercutie.core.enums import Severity
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.dedup import worker
from pagercutie.pipeline.dedup.windows import DIRTY_KEY, RedisWindowStore
from pagercutie.pipeline.messages import AlertContent, Event, Match, Opened, Renotified, Repeated
from pagercutie.rules import service as rules
from pagercutie.rules.ast import Exists
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, TeamRecipient
from pagercutie.teams.models import Team
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)
WINDOW = timedelta(seconds=300)
FINGERPRINT = "a" * 64
WON = dedup.Won(key="dedup:rule:fingerprint")
PENDING = dedup.Pending(key="dedup:rule:fingerprint")
UNAVAILABLE = dedup.Unavailable(key="dedup:rule:fingerprint")


def make_rule(team: Team, *, user: User | None = None) -> Rule:
    return Rule(
        name="Settlement failed",
        description=None,
        enabled=True,
        team_id=None if user else team.id,
        user_id=user.id if user else None,
        schema_ids=[],
        condition=Exists(op="exists", field="payload.workflowId"),
        dedup=Dedup(fields=["payload.workflowId"], window_s=int(WINDOW.total_seconds())),
        routing=Routing(recipients=[TeamRecipient(type="team", team_id=team.id)]),
        presentation=Presentation(
            title="Workflow {{workflowId}} failed",
            body="{{severity}} from {{source}}: {{payload.error.code}}",
            fields=["payload.error.code", "payload.missing"],
            severity=Severity.CRITICAL,
            colour=Colour.RED,
        ),
        runbook_id=None,
    )


async def add_rule(session: AsyncSession, rule: Rule) -> Rule:
    session.add(rule)
    await session.flush()
    await session.refresh(rule)
    return rule


def make_match(rule: Rule, team: Team, received_at: datetime = NOW, fingerprint: str = FINGERPRINT) -> Match:
    event = Event(
        event_id=uuid.uuid7(),
        source="payments-webhook",
        source_id=uuid.uuid7(),
        team_id=team.id,
        schema_id=uuid.uuid7(),
        schema_name="payment",
        severity=Severity.ERROR,
        received_at=received_at,
        payload={"workflowId": "wf-1", "error": {"code": "TIMEOUT"}},
    )
    return Match(event=event, rule=rules.to_read(rule), fingerprint=fingerprint)


@pytest.fixture
async def team(session: AsyncSession) -> Team:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    return team


@pytest.fixture
async def rule(session: AsyncSession, team: Team) -> Rule:
    return await add_rule(session, make_rule(team))


async def load(session: AsyncSession, alert_id: uuid.UUID) -> Alert:
    return await session.get_one(Alert, alert_id, populate_existing=True)


async def audited(session: AsyncSession) -> list[AuditEntry]:
    return list(await session.scalars(select(AuditEntry).order_by(AuditEntry.id)))


async def test_the_first_match_opens_an_alert_rendered_from_the_rule(
    session: AsyncSession, team: Team, rule: Rule
) -> None:
    match = make_match(rule, team)

    outcome = await dedup.record(session, match, WON)

    assert isinstance(outcome, Opened)
    assert outcome.match == match
    alert = await load(session, outcome.alert_id)
    assert (alert.rule_id, alert.team_id, alert.fingerprint) == (rule.id, team.id, FINGERPRINT)
    assert (alert.status, alert.severity, alert.colour) == (AlertStatus.OPEN, Severity.CRITICAL, Colour.RED)
    assert alert.title == "Workflow wf-1 failed"
    assert alert.body == "error from payments-webhook: TIMEOUT"
    assert alert.fields == [
        AlertField(path="payload.error.code", value="TIMEOUT"),
        AlertField(path="payload.missing", value=None),
    ]
    assert (alert.occurrences, alert.notifications) == (1, 1)
    assert alert.first_seen_at == alert.last_seen_at == alert.notified_at == NOW
    assert alert.payload == match.event.payload
    assert alert.escalated_team_ids == []
    assert outcome.team_id == team.id
    assert outcome.content == AlertContent(severity=alert.severity, title=alert.title, body=alert.body)
    (entry,) = await audited(session)
    assert (entry.actor_user_id, entry.action, entry.entity_id, entry.team_id) == (
        None,
        AuditAction.ALERT_CREATED,
        alert.id,
        team.id,
    )
    assert entry.data == {"rule_id": str(rule.id), "event_id": str(match.event.event_id)}


async def test_a_personal_rule_opens_an_alert_without_a_team(session: AsyncSession, team: Team) -> None:
    anna = User(email="anna@example.com", display_name="Anna", timezone="UTC", role=GlobalRole.USER)
    session.add(anna)
    await session.flush()
    personal = await add_rule(session, make_rule(team, user=anna))

    outcome = await dedup.record(session, make_match(personal, team), WON)

    assert isinstance(outcome, Opened)
    assert outcome.team_id is None
    assert (await load(session, outcome.alert_id)).team_id is None


@pytest.mark.parametrize("claim", [WON, PENDING, UNAVAILABLE], ids=["won", "pending", "unavailable"])
async def test_a_match_inside_the_window_is_a_repeat_whatever_the_claim(
    session: AsyncSession, team: Team, rule: Rule, claim: dedup.Recordable
) -> None:
    opened = await dedup.record(session, make_match(rule, team), WON)
    later = NOW + WINDOW - timedelta(seconds=1)

    outcome = await dedup.record(session, make_match(rule, team, later), claim)

    assert outcome == Repeated(alert_id=opened.alert_id, match=outcome.match)
    alert = await load(session, opened.alert_id)
    assert (alert.occurrences, alert.notifications, alert.last_seen_at, alert.notified_at) == (2, 1, later, NOW)
    assert [entry.action for entry in await audited(session)] == [AuditAction.ALERT_CREATED]


@pytest.mark.parametrize("claim", [WON, PENDING, UNAVAILABLE], ids=["won", "pending", "unavailable"])
async def test_a_match_a_window_after_the_last_notification_renotifies_whatever_the_claim(
    session: AsyncSession, team: Team, rule: Rule, claim: dedup.Recordable
) -> None:
    opened = await dedup.record(session, make_match(rule, team), WON)
    assert isinstance(opened, Opened)
    later = NOW + WINDOW
    # A newer rule snapshot must not change what the existing alert renders.
    edited = make_match(rule, team, later)
    edited = edited.model_copy(
        update={
            "rule": edited.rule.model_copy(
                update={"presentation": Presentation(title="New", severity=Severity.INFO, colour=Colour.RED)}
            )
        }
    )

    outcome = await dedup.record(session, edited, claim)

    assert outcome == Renotified(
        alert_id=opened.alert_id, content=opened.content, match=outcome.match, notification_seq=2
    )
    alert = await load(session, opened.alert_id)
    assert (alert.occurrences, alert.notifications, alert.notified_at) == (2, 2, later)
    _, renotified = await audited(session)
    assert (renotified.action, renotified.entity_id) == (AuditAction.ALERT_RENOTIFIED, alert.id)
    assert renotified.data == {"notification_seq": 2, "event_id": str(outcome.match.event.event_id)}


async def test_an_older_event_does_not_move_last_seen_back(session: AsyncSession, team: Team, rule: Rule) -> None:
    opened = await dedup.record(session, make_match(rule, team), WON)

    await dedup.record(session, make_match(rule, team, NOW - timedelta(seconds=10)), PENDING)

    assert (await load(session, opened.alert_id)).last_seen_at == NOW


async def test_a_match_after_the_alert_is_resolved_opens_a_new_alert(
    session: AsyncSession, team: Team, rule: Rule
) -> None:
    first = await dedup.record(session, make_match(rule, team), WON)
    alert = await load(session, first.alert_id)
    alert.status, alert.resolved_at, alert.resolution = AlertStatus.RESOLVED, NOW, Resolution.MANUAL
    await session.flush()

    second = await dedup.record(session, make_match(rule, team, NOW + timedelta(seconds=1)), PENDING)

    assert isinstance(second, Opened)
    assert second.alert_id != first.alert_id


async def test_other_fingerprints_open_their_own_alerts(session: AsyncSession, team: Team, rule: Rule) -> None:
    first = await dedup.record(session, make_match(rule, team), WON)
    second = await dedup.record(session, make_match(rule, team, fingerprint="b" * 64), WON)

    assert isinstance(second, Opened)
    assert second.alert_id != first.alert_id


@pytest.fixture
async def committed_rule(engine: AsyncEngine) -> AsyncIterator[tuple[Team, Rule]]:
    """A team and rule committed for real, so two connections can race on them; removed afterwards."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        team = Team(slug=f"race-{uuid.uuid7().hex[:8]}", name="Race")
        session.add(team)
        await session.flush()
        rule = await add_rule(session, make_rule(team))
        await session.commit()
    yield team, rule
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(delete(Alert).where(Alert.rule_id == rule.id))
        await session.execute(delete(Rule).where(Rule.id == rule.id))
        await session.execute(delete(Team).where(Team.id == team.id))


async def test_a_match_racing_the_winner_makes_the_winner_a_repeat(
    engine: AsyncEngine, committed_rule: tuple[Team, Rule]
) -> None:
    team, rule = committed_rule
    async with AsyncSession(engine) as fallback, AsyncSession(engine) as winner:
        await fallback.begin()
        opened = await dedup.record(fallback, make_match(rule, team), PENDING)
        await winner.begin()
        racing = asyncio.create_task(dedup.record(winner, make_match(rule, team), WON))
        await asyncio.sleep(0.2)
        assert not racing.done(), "the winner's upsert must wait for the fallback's row"
        await fallback.commit()
        outcome = await racing
        await winner.commit()

    assert isinstance(opened, Opened)
    assert outcome == Repeated(alert_id=opened.alert_id, match=outcome.match)
    async with AsyncSession(engine) as session:
        alerts = (await session.scalars(select(Alert).where(Alert.rule_id == rule.id))).all()
    assert [(a.occurrences, a.notifications) for a in alerts] == [(2, 1)]


class FailingSessions(async_sessionmaker[AsyncSession]):
    def __call__(self, **local_kw: object) -> AsyncSession:
        raise ConnectionError("database down")


@pytest.fixture
def windows(redis: Redis) -> RedisWindowStore:
    return RedisWindowStore(redis)


async def test_the_flush_adds_redis_counts_and_the_newest_time_to_the_alert(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    redis: Redis,
    team: Team,
    rule: Rule,
) -> None:
    opened = await dedup.record(session, make_match(rule, team), WON)
    await session.flush()
    for seconds in (1, 3, 2):
        await windows.increment(opened.alert_id, NOW + timedelta(seconds=seconds))

    assert await worker.flush_counters(sessionmaker, windows) == 1

    alert = await load(session, opened.alert_id)
    assert (alert.occurrences, alert.last_seen_at) == (4, NOW + timedelta(seconds=3))
    assert await redis.exists(DIRTY_KEY) == 0


async def test_the_flush_never_moves_last_seen_back(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    team: Team,
    rule: Rule,
) -> None:
    opened = await dedup.record(session, make_match(rule, team), WON)
    await session.flush()
    await windows.increment(opened.alert_id, NOW - timedelta(seconds=30))

    await worker.flush_counters(sessionmaker, windows)

    assert (await load(session, opened.alert_id)).last_seen_at == NOW


async def test_the_flush_drains_every_batch(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    team: Team,
    rule: Rule,
) -> None:
    alerts = [await dedup.record(session, make_match(rule, team, fingerprint=c * 64), WON) for c in "abc"]
    await session.flush()
    for outcome in alerts:
        await windows.increment(outcome.alert_id, NOW)

    assert await worker.flush_counters(sessionmaker, windows, batch=2) == 3
    assert [(await load(session, outcome.alert_id)).occurrences for outcome in alerts] == [2, 2, 2]


async def test_a_failed_flush_puts_the_counts_back_for_the_next_one(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    team: Team,
    rule: Rule,
) -> None:
    opened = await dedup.record(session, make_match(rule, team), WON)
    await session.flush()
    await windows.increment(opened.alert_id, NOW)

    with pytest.raises(ConnectionError):
        await worker.flush_counters(FailingSessions(), windows)
    await worker.flush_counters(sessionmaker, windows)

    assert (await load(session, opened.alert_id)).occurrences == 2


async def test_the_loop_flushes_once_more_when_the_replica_stops(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    team: Team,
    rule: Rule,
) -> None:
    opened = await dedup.record(session, make_match(rule, team), WON)
    await session.flush()
    await windows.increment(opened.alert_id, NOW)
    stopping = asyncio.Event()
    stopping.set()

    await worker.counter_flush(sessionmaker, windows)(stopping)

    assert (await load(session, opened.alert_id)).occurrences == 2


async def test_the_loop_survives_a_failed_flush(windows: RedisWindowStore) -> None:
    await windows.increment(uuid.uuid7(), NOW)
    stopping = asyncio.Event()
    stopping.set()

    await worker.counter_flush(FailingSessions(), windows)(stopping)

    assert len(await windows.drain(10)) == 1
