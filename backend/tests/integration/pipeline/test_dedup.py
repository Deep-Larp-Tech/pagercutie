import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import structlog
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pagercutie.alerts import service as alerts
from pagercutie.alerts.models import Alert
from pagercutie.alerts.schemas import AlertField, AlertStatus, Resolution, ResolveRequest
from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction
from pagercutie.auth.service import CurrentUser
from pagercutie.core.enums import Severity
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.dedup import worker
from pagercutie.pipeline.dedup.windows import BATCHES_KEY, DIRTY_KEY, RedisWindowStore
from pagercutie.pipeline.messages import DedupOutcome, Event, Match, Opened, Renotified, Repeated
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


async def record(session: AsyncSession, match: Match, claim: dedup.Recordable) -> DedupOutcome:
    return (await dedup.record(session, match, claim)).outcome


async def load(session: AsyncSession, alert_id: uuid.UUID) -> Alert:
    return await session.get_one(Alert, alert_id, populate_existing=True)


async def audited(session: AsyncSession) -> list[AuditEntry]:
    return list(await session.scalars(select(AuditEntry).order_by(AuditEntry.id)))


async def test_the_first_match_opens_an_alert_rendered_from_the_rule(
    session: AsyncSession, team: Team, rule: Rule
) -> None:
    match = make_match(rule, team)

    outcome = await record(session, match, WON)

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

    outcome = await record(session, make_match(personal, team), WON)

    assert (await load(session, outcome.alert_id)).team_id is None


@pytest.mark.parametrize("claim", [WON, PENDING, UNAVAILABLE], ids=["won", "pending", "unavailable"])
async def test_a_match_inside_the_window_is_a_repeat_whatever_the_claim(
    session: AsyncSession, team: Team, rule: Rule, claim: dedup.Recordable
) -> None:
    opened = await record(session, make_match(rule, team), WON)
    later = NOW + WINDOW - timedelta(seconds=1)

    outcome = await record(session, make_match(rule, team, later), claim)

    assert outcome == Repeated(alert_id=opened.alert_id, match=outcome.match)
    alert = await load(session, opened.alert_id)
    assert (alert.occurrences, alert.notifications, alert.last_seen_at, alert.notified_at) == (2, 1, later, NOW)
    assert [entry.action for entry in await audited(session)] == [AuditAction.ALERT_CREATED]


@pytest.mark.parametrize("claim", [WON, PENDING, UNAVAILABLE], ids=["won", "pending", "unavailable"])
async def test_a_match_a_window_after_the_last_notification_renotifies_whatever_the_claim(
    session: AsyncSession, team: Team, rule: Rule, claim: dedup.Recordable
) -> None:
    opened = await record(session, make_match(rule, team), WON)
    later = NOW + WINDOW

    outcome = await record(session, make_match(rule, team, later), claim)

    assert isinstance(outcome, Renotified)
    assert (outcome.alert_id, outcome.notification_seq) == (opened.alert_id, 2)
    assert (outcome.team_id, outcome.title) == (team.id, "Workflow wf-1 failed")
    alert = await load(session, opened.alert_id)
    assert (alert.occurrences, alert.notifications, alert.notified_at) == (2, 2, later)
    _, renotified = await audited(session)
    assert (renotified.action, renotified.entity_id) == (AuditAction.ALERT_RENOTIFIED, alert.id)
    assert renotified.data == {"notification_seq": 2, "event_id": str(outcome.match.event.event_id)}


async def test_an_older_event_does_not_move_last_seen_back(session: AsyncSession, team: Team, rule: Rule) -> None:
    opened = await record(session, make_match(rule, team), WON)

    await record(session, make_match(rule, team, NOW - timedelta(seconds=10)), PENDING)

    assert (await load(session, opened.alert_id)).last_seen_at == NOW


async def test_a_match_after_the_alert_is_resolved_opens_a_new_alert(
    session: AsyncSession, team: Team, rule: Rule
) -> None:
    first = await record(session, make_match(rule, team), WON)
    alert = await load(session, first.alert_id)
    alert.status, alert.resolved_at, alert.resolution = AlertStatus.RESOLVED, NOW, Resolution.MANUAL
    await session.flush()

    second = await record(session, make_match(rule, team, NOW + timedelta(seconds=1)), PENDING)

    assert isinstance(second, Opened)
    assert second.alert_id != first.alert_id


async def test_other_fingerprints_open_their_own_alerts(session: AsyncSession, team: Team, rule: Rule) -> None:
    first = await record(session, make_match(rule, team), WON)
    second = await record(session, make_match(rule, team, fingerprint="b" * 64), WON)

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
        opened = await record(fallback, make_match(rule, team), PENDING)
        await winner.begin()
        racing = asyncio.create_task(record(winner, make_match(rule, team), WON))
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


async def count(windows: RedisWindowStore, redis: Redis, alert_id: uuid.UUID, seen_at: datetime = NOW) -> None:
    """Count one occurrence of the alert the way ingest does: a claim on a window that holds it."""
    key = f"dedup:held:{alert_id}"
    await redis.set(key, str(alert_id))
    request = dedup.ClaimRequest(key=key, window_s=300, token="pending:test", seen_at=seen_at)
    assert await windows.claim([request]) == [dedup.Held(key=key, alert_id=alert_id)]


async def test_the_flush_adds_redis_counts_and_the_newest_time_to_the_alert(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    redis: Redis,
    team: Team,
    rule: Rule,
) -> None:
    opened = await record(session, make_match(rule, team), WON)
    await session.flush()
    for seconds in (1, 3, 2):
        await count(windows, redis, opened.alert_id, NOW + timedelta(seconds=seconds))

    assert await worker.flush_counters(sessionmaker, windows) == 1

    alert = await load(session, opened.alert_id)
    assert (alert.occurrences, alert.last_seen_at) == (4, NOW + timedelta(seconds=3))
    assert await redis.exists(DIRTY_KEY) == 0


async def test_the_flush_never_moves_last_seen_back(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    redis: Redis,
    team: Team,
    rule: Rule,
) -> None:
    opened = await record(session, make_match(rule, team), WON)
    await session.flush()
    await count(windows, redis, opened.alert_id, NOW - timedelta(seconds=30))

    await worker.flush_counters(sessionmaker, windows)

    assert (await load(session, opened.alert_id)).last_seen_at == NOW


async def test_the_flush_drains_every_batch(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    redis: Redis,
    team: Team,
    rule: Rule,
) -> None:
    alerts = [await record(session, make_match(rule, team, fingerprint=c * 64), WON) for c in "abc"]
    await session.flush()
    for outcome in alerts:
        await count(windows, redis, outcome.alert_id, NOW)

    assert await worker.flush_counters(sessionmaker, windows, batch=2) == 3
    assert [(await load(session, outcome.alert_id)).occurrences for outcome in alerts] == [2, 2, 2]


async def test_a_failed_flush_puts_the_counts_back_for_the_next_one(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    redis: Redis,
    team: Team,
    rule: Rule,
) -> None:
    opened = await record(session, make_match(rule, team), WON)
    await session.flush()
    await count(windows, redis, opened.alert_id, NOW)

    with pytest.raises(ConnectionError):
        await worker.flush_counters(FailingSessions(), windows)
    await worker.flush_counters(sessionmaker, windows)

    assert (await load(session, opened.alert_id)).occurrences == 2


async def test_the_loop_flushes_once_more_when_the_replica_stops(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    redis: Redis,
    team: Team,
    rule: Rule,
) -> None:
    opened = await record(session, make_match(rule, team), WON)
    await session.flush()
    await count(windows, redis, opened.alert_id, NOW)
    stopping = asyncio.Event()
    stopping.set()

    await worker.counter_flush(sessionmaker, windows)(stopping)

    assert (await load(session, opened.alert_id)).occurrences == 2


async def test_the_loop_survives_a_failed_flush(windows: RedisWindowStore, redis: Redis) -> None:
    await count(windows, redis, uuid.uuid7(), NOW)
    stopping = asyncio.Event()
    stopping.set()

    await worker.counter_flush(FailingSessions(), windows)(stopping)

    assert len(await windows.drain("check", 10)) == 1


async def test_the_flush_forgets_its_batch_once_committed(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    redis: Redis,
    team: Team,
    rule: Rule,
) -> None:
    opened = await record(session, make_match(rule, team), WON)
    await session.flush()
    await count(windows, redis, opened.alert_id)

    await worker.flush_counters(sessionmaker, windows)

    assert await redis.exists(BATCHES_KEY) == 0
    assert await windows.recover(0) == 0


async def test_a_batch_left_by_a_flush_that_died_is_recovered_and_applied(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    redis: Redis,
    team: Team,
    rule: Rule,
) -> None:
    opened = await record(session, make_match(rule, team), WON)
    await session.flush()
    await count(windows, redis, opened.alert_id)
    # A replica drained this batch, or lost the drain's reply, and never committed it.
    await windows.drain("dead-replica", 10)
    assert await worker.flush_counters(sessionmaker, windows) == 0

    monkeypatch.setattr(worker, "RECOVER_AFTER_S", 0)
    assert await worker.flush_counters(sessionmaker, windows) == 1

    assert (await load(session, opened.alert_id)).occurrences == 2


async def test_the_flush_reports_counts_of_resolved_and_missing_alerts(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    redis: Redis,
    team: Team,
    rule: Rule,
) -> None:
    resolved = await record(session, make_match(rule, team), WON)
    alert = await load(session, resolved.alert_id)
    alert.status, alert.resolved_at, alert.resolution = AlertStatus.RESOLVED, NOW, Resolution.MANUAL
    await session.flush()
    missing = uuid.uuid7()
    await count(windows, redis, resolved.alert_id)
    await count(windows, redis, missing)

    with structlog.testing.capture_logs() as logs:
        assert await worker.flush_counters(sessionmaker, windows) == 2

    assert (await load(session, resolved.alert_id)).occurrences == 2
    reported = {entry["event"]: entry["alert_ids"] for entry in logs if "alert_ids" in entry}
    assert reported == {
        "dedup.counters_on_resolved": [str(resolved.alert_id)],
        "dedup.counters_dropped": [str(missing)],
    }
    assert await redis.exists(DIRTY_KEY, BATCHES_KEY) == 0


async def settle(
    sessionmaker: async_sessionmaker[AsyncSession], windows: RedisWindowStore, match: Match
) -> tuple[dedup.Claim, DedupOutcome]:
    """Runs one match through a dedup scope the way the orchestrator does; a held window records nothing."""
    async with dedup.deduplicate([match], windows) as scope:
        if not scope.to_record:
            [repeat] = scope.repeated
            return dedup.Held(key=dedup.window_key(match), alert_id=repeat.alert_id), repeat
        [item] = scope.to_record
        async with sessionmaker() as session, session.begin():
            outcome = await scope.record(session, item)
    return item.claim, outcome


async def test_a_repeat_on_a_won_window_keeps_it_only_for_the_rest_of_the_alerts_round(
    sessionmaker: async_sessionmaker[AsyncSession], windows: RedisWindowStore, redis: Redis, team: Team, rule: Rule
) -> None:
    now = datetime.now(UTC)
    _, opened = await settle(sessionmaker, windows, make_match(rule, team, now - timedelta(seconds=100)))
    # Redis restarted empty: the next match wins a window although the alert's round is two thirds over.
    await redis.flushdb()

    claim, outcome = await settle(sessionmaker, windows, make_match(rule, team, now))

    assert (type(claim), type(outcome), outcome.alert_id) == (dedup.Won, Repeated, opened.alert_id)
    key = dedup.window_key(outcome.match)
    assert await redis.get(key) == str(opened.alert_id)
    assert 195 <= await redis.ttl(key) <= 200


async def test_a_match_after_a_resolve_opens_a_new_alert(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    windows: RedisWindowStore,
    team: Team,
    rule: Rule,
) -> None:
    admin = User(email="admin@example.com", display_name="Admin", timezone="UTC", role=GlobalRole.ADMIN)
    session.add(admin)
    await session.flush()
    actor = CurrentUser(id=admin.id, role=GlobalRole.ADMIN, session_token_hash=b"")
    now = datetime.now(UTC)
    _, first = await settle(sessionmaker, windows, make_match(rule, team, now))
    held, _ = await settle(sessionmaker, windows, make_match(rule, team, now + timedelta(seconds=1)))
    assert held == dedup.Held(key=dedup.window_key(first.match), alert_id=first.alert_id)

    async with sessionmaker() as resolving, resolving.begin():
        await alerts.resolve_alert(resolving, actor, first.alert_id, ResolveRequest(), windows)
    claim, second = await settle(sessionmaker, windows, make_match(rule, team, now + timedelta(seconds=2)))

    assert (type(claim), type(second)) == (dedup.Won, Opened)
    assert second.alert_id != first.alert_id
    assert (await load(session, first.alert_id)).occurrences == 1


async def test_a_match_during_an_uncommitted_resolve_waits_and_opens_a_new_alert(
    engine: AsyncEngine, committed_rule: tuple[Team, Rule], windows: RedisWindowStore
) -> None:
    team, rule = committed_rule
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    _, first = await settle(sessions, windows, make_match(rule, team, now))
    async with AsyncSession(engine) as resolving:
        await resolving.begin()
        # What `alerts.service.resolve_alert` does before its commit.
        alert = await resolving.get_one(Alert, first.alert_id, with_for_update=True)
        alert.status, alert.resolved_at, alert.resolution = AlertStatus.RESOLVED, now, Resolution.MANUAL
        await resolving.flush()
        await windows.mark_resolved(alert.id, rule.id, alert.fingerprint)
        racing = asyncio.create_task(settle(sessions, windows, make_match(rule, team, now + timedelta(seconds=1))))
        await asyncio.sleep(0.2)
        assert not racing.done(), "the match's upsert must wait for the resolving transaction"
        await resolving.commit()
    claim, second = await racing

    assert (type(claim), type(second)) == (dedup.Won, Opened)
    assert second.alert_id != first.alert_id
