import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from tests.integration.pipeline.test_dedup import add_rule, make_rule
from tests.integration.pipeline.test_dedup import make_match as make_recorded_match
from tests.integration.pipeline.test_executor_start import STEPS
from tests.integration.pipeline.test_routing import add_members, make_team, make_user, preferences

from pagercutie.alerts.models import Delivery, RunbookRun
from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction
from pagercutie.core.enums import Channel, Severity
from pagercutie.pipeline import orchestrator
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.pipeline.executor import stage as executor
from pagercutie.pipeline.ingest import stage as ingest
from pagercutie.pipeline.messages import (
    AlertContent,
    DedupOutcome,
    Event,
    Match,
    Opened,
    RawEvent,
    Renotified,
    Repeated,
)
from pagercutie.pipeline.routing import stage as routing
from pagercutie.rules.schemas import RuleRead
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.sources.schemas import SourceType
from pagercutie.teams.schemas import TeamRole

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 21, tzinfo=UTC)
RAW = RawEvent(
    source_slug="payments-webhook",
    source_type=SourceType.WEBHOOK,
    token="t",
    content_type="application/json",
    body=b"{}",
)
CATALOG = ingest.SourceCatalog(sources={})
RULES = evaluation.RuleSet(by_schema={}, any_schema=[])
EVENT = Event(
    event_id=uuid.uuid7(),
    source="payments-webhook",
    source_id=uuid.uuid7(),
    team_id=uuid.uuid7(),
    schema_id=uuid.uuid7(),
    schema_name="payment",
    severity=Severity.CRITICAL,
    received_at=NOW,
    payload={"workflowId": "wf-1"},
)


def make_match() -> Match:
    rule = RuleRead.model_validate(
        {
            "id": uuid.uuid7(),
            "name": "Settlement failed",
            "description": None,
            "enabled": True,
            "owner": {"type": "team", "team_id": EVENT.team_id},
            "schema_ids": [],
            "condition": {"op": "exists", "field": "payload.workflowId"},
            "dedup": {"fields": ["payload.workflowId"], "window_s": 300},
            "routing": {"recipients": [{"type": "on_call", "team_id": EVENT.team_id}]},
            "presentation": {"title": "Failed", "severity": "critical", "colour": "red"},
            "runbook_id": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
    )
    return Match(event=EVENT, rule=rule, fingerprint=uuid.uuid4().hex)


CONTENT = AlertContent(severity=Severity.CRITICAL, title="Failed", body=None)


def opened(match: Match) -> Opened:
    return Opened(alert_id=uuid.uuid7(), team_id=EVENT.team_id, content=CONTENT, match=match)


def renotified(match: Match) -> Renotified:
    return Renotified(alert_id=uuid.uuid7(), content=CONTENT, match=match, notification_seq=2)


def repeated(match: Match) -> Repeated:
    return Repeated(alert_id=uuid.uuid7(), match=match)


class NoSessions(async_sessionmaker[AsyncSession]):
    def __call__(self, **local_kw: object) -> AsyncSession:
        raise AssertionError("this event must not open a transaction")


class FakeWindows:
    """Answers each claim from `claims`, by window key."""

    def __init__(self, claims: dict[str, dedup.Claim]) -> None:
        self.claims = claims

    async def claim(self, key: str, window_s: int) -> dedup.Claim:
        return self.claims[key]

    async def confirm(self, key: str, alert_id: uuid.UUID) -> None:
        pass

    async def release(self, key: str) -> None:
        pass

    async def increment(self, alert_id: uuid.UUID, seen_at: datetime) -> None:
        pass

    async def drain(self, limit: int) -> list[dedup.Counter]:
        return []

    async def restore(self, counters: Sequence[dedup.Counter]) -> None:
        pass


class Calls:
    """Replaces the stage entrypoints the orchestrator calls and records what they were called with."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, matches: list[Match]) -> None:
        self.recorded: list[Match] = []
        self.routed: list[Opened | Renotified] = []
        self.started: list[Opened] = []
        self.repeated: list[Match] = []
        self.confirmed: list[tuple[dedup.Claim, DedupOutcome]] = []
        self.released: list[dedup.Claim] = []
        # What `record` returns per window key; `Opened` when absent.
        self.outcomes: dict[str, Callable[[Match], DedupOutcome]] = {}
        self.record_error: Exception | None = None

        async def normalise(raw: RawEvent, catalog: ingest.SourceCatalog, load_schemas: ingest.SchemaLoader) -> Event:
            return EVENT

        def evaluate(event: Event, rules: evaluation.RuleSet) -> list[Match]:
            return matches

        async def record(session: AsyncSession, match: Match, claim: dedup.Recordable) -> DedupOutcome:
            if self.record_error:
                raise self.record_error
            self.recorded.append(match)
            return self.outcomes.get(claim.key, opened)(match)

        async def repeat(match: Match, claim: dedup.Held, windows: dedup.WindowStore) -> Repeated:
            self.repeated.append(match)
            return Repeated(alert_id=claim.alert_id, match=match)

        async def confirm(claim: dedup.Claim, outcome: DedupOutcome, windows: dedup.WindowStore) -> None:
            self.confirmed.append((claim, outcome))

        async def release(claim: dedup.Claim, windows: dedup.WindowStore) -> None:
            self.released.append(claim)

        async def route(session: AsyncSession, outcome: Opened | Renotified) -> list[uuid.UUID]:
            self.routed.append(outcome)
            return []

        async def start_run(session: AsyncSession, opened: Opened) -> uuid.UUID | None:
            self.started.append(opened)
            return None

        monkeypatch.setattr(ingest, "normalise", normalise)
        monkeypatch.setattr(evaluation, "evaluate", evaluate)
        monkeypatch.setattr(dedup, "record", record)
        monkeypatch.setattr(dedup, "repeat", repeat)
        monkeypatch.setattr(dedup, "confirm", confirm)
        monkeypatch.setattr(dedup, "release", release)
        monkeypatch.setattr(routing, "route", route)
        monkeypatch.setattr(executor, "start_run", start_run)


async def test_a_new_alert_is_routed_its_runbook_started_and_its_window_confirmed(
    monkeypatch: pytest.MonkeyPatch, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    match = make_match()
    calls = Calls(monkeypatch, [match])
    won = dedup.Won(key=dedup.window_key(match))

    result = await orchestrator.process_event(RAW, sessionmaker, CATALOG, RULES, FakeWindows({won.key: won}))

    assert (result.event_id, result.matches) == (EVENT.event_id, 1)
    assert calls.recorded == [match]
    assert [o.match for o in calls.routed] == [match]
    assert [o.match for o in calls.started] == [match]
    assert [(claim, type(outcome)) for claim, outcome in calls.confirmed] == [(won, Opened)]
    assert calls.released == []


async def test_a_renotified_alert_is_routed_without_a_new_runbook_run(
    monkeypatch: pytest.MonkeyPatch, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    match = make_match()
    calls = Calls(monkeypatch, [match])
    won = dedup.Won(key=dedup.window_key(match))
    calls.outcomes[won.key] = renotified

    await orchestrator.process_event(RAW, sessionmaker, CATALOG, RULES, FakeWindows({won.key: won}))

    assert [type(o) for o in calls.routed] == [Renotified]
    assert calls.started == []


async def test_a_repeat_recorded_in_postgres_is_neither_routed_nor_run(
    monkeypatch: pytest.MonkeyPatch, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    match = make_match()
    calls = Calls(monkeypatch, [match])
    pending = dedup.Pending(key=dedup.window_key(match))
    calls.outcomes[pending.key] = repeated

    await orchestrator.process_event(RAW, sessionmaker, CATALOG, RULES, FakeWindows({pending.key: pending}))

    assert calls.recorded == [match]
    assert (calls.routed, calls.started) == ([], [])


async def test_a_held_window_is_counted_in_redis_without_a_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    match = make_match()
    calls = Calls(monkeypatch, [match])
    held = dedup.Held(key=dedup.window_key(match), alert_id=uuid.uuid7())

    await orchestrator.process_event(RAW, NoSessions(), CATALOG, RULES, FakeWindows({held.key: held}))

    assert calls.repeated == [match]
    assert calls.recorded == []
    assert [type(outcome) for _, outcome in calls.confirmed] == [Repeated]


async def test_a_failed_record_releases_every_claim_and_confirms_none(
    monkeypatch: pytest.MonkeyPatch, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    first, second = make_match(), make_match()
    calls = Calls(monkeypatch, [first, second])
    calls.record_error = RuntimeError("database down")
    won = dedup.Won(key=dedup.window_key(first))
    unavailable = dedup.Unavailable(key=dedup.window_key(second))
    windows = FakeWindows({won.key: won, unavailable.key: unavailable})

    with pytest.raises(RuntimeError, match="database down"):
        await orchestrator.process_event(RAW, sessionmaker, CATALOG, RULES, windows)

    assert calls.released == [won, unavailable]
    assert calls.confirmed == []


async def test_an_event_without_matches_touches_no_window(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch, [])

    result = await orchestrator.process_event(RAW, NoSessions(), CATALOG, RULES, FakeWindows({}))

    assert result.matches == 0
    assert (calls.recorded, calls.confirmed, calls.released) == ([], [], [])


async def test_an_opened_alert_is_recorded_routed_and_run_without_rereading_its_rows(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    session: AsyncSession,
) -> None:
    team = await make_team(session, preferences(Channel.EMAIL))
    anna, boris = await make_user(session, "anna"), await make_user(session, "boris")
    await add_members(session, team, {anna: TeamRole.LEAD, boris: TeamRole.MEMBER})
    runbook = Runbook(
        slug="retry", title="Retry", team_id=team.id, format=RunbookFormat.STRUCTURED, original="", steps=STEPS
    )
    session.add(runbook)
    await session.flush()
    rule = make_rule(team)
    rule.runbook_id = runbook.id
    match = make_recorded_match(await add_rule(session, rule), team)

    async def normalise(raw: RawEvent, catalog: ingest.SourceCatalog, load_schemas: ingest.SchemaLoader) -> Event:
        return match.event

    def evaluate(event: Event, rules: evaluation.RuleSet) -> list[Match]:
        return [match]

    monkeypatch.setattr(ingest, "normalise", normalise)
    monkeypatch.setattr(evaluation, "evaluate", evaluate)
    won = dedup.Won(key=dedup.window_key(match))
    statements: list[str] = []

    def collect(conn: Connection, cursor: object, statement: str, *args: object) -> None:
        # The fixture's savepoints stand in for the real transaction's BEGIN and COMMIT.
        if not statement.startswith(("SAVEPOINT", "RELEASE SAVEPOINT")):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", collect)
    try:
        await orchestrator.process_event(RAW, sessionmaker, CATALOG, RULES, FakeWindows({won.key: won}))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", collect)

    # Upsert, its NOTIFY, team, members, deliveries, their NOTIFY, runbook, run, steps, their NOTIFY, and the two
    # audit entries in one INSERT at commit: no statement re-reads the alert row.
    assert len(statements) == 11
    assert not [s for s in statements if s.startswith("SELECT alerts.")]
    deliveries = select(func.count()).select_from(Delivery).where(Delivery.user_id.in_([anna.id, boris.id]))
    assert await session.scalar(deliveries) == 4
    runs = select(func.count()).select_from(RunbookRun).where(RunbookRun.runbook_id == runbook.id)
    assert await session.scalar(runs) == 1
    actions = await session.scalars(
        select(AuditEntry.action).where(AuditEntry.team_id == team.id).order_by(AuditEntry.id)
    )
    assert list(actions) == [AuditAction.ALERT_CREATED, AuditAction.RUNBOOK_RUN_STARTED]
