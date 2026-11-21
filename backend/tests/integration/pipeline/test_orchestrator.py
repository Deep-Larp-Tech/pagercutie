import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_windows import FakeWindows
from pagercutie.core.enums import Severity
from pagercutie.pipeline import orchestrator
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.pipeline.executor import stage as executor
from pagercutie.pipeline.ingest import stage as ingest
from pagercutie.pipeline.messages import DedupOutcome, Event, Match, Opened, RawEvent, Renotified, Repeated
from pagercutie.pipeline.routing import stage as routing
from pagercutie.rules.schemas import RuleRead
from pagercutie.sources.schemas import SeverityMapping, SourceType
from pagercutie.sources.service import IngestSource
from pagercutie.teams.models import Team

pytestmark = pytest.mark.anyio

NOW = datetime.now(UTC)
TEAM_ID = uuid.uuid7()
RAW = RawEvent(
    source=IngestSource(
        id=uuid.uuid7(),
        slug="payments-webhook",
        type=SourceType.WEBHOOK,
        team_id=TEAM_ID,
        severity=SeverityMapping(),
        token_hash=b"",
    ),
    body=b"{}",
)
RULES = evaluation.RuleSet(by_schema={}, any_schema=[])
EVENT = Event(
    event_id=uuid.uuid7(),
    source="payments-webhook",
    source_id=RAW.source.id,
    team_id=TEAM_ID,
    schema_id=uuid.uuid7(),
    schema_name="payment",
    severity=Severity.CRITICAL,
    received_at=NOW,
    payload={"workflowId": "wf-1"},
)


async def no_schemas(team_id: uuid.UUID) -> list[ingest.CompiledSchema]:
    raise AssertionError("normalise is replaced")


def make_match() -> Match:
    rule = RuleRead.model_validate(
        {
            "id": uuid.uuid7(),
            "name": "Settlement failed",
            "description": None,
            "enabled": True,
            "owner": {"type": "team", "team_id": TEAM_ID},
            "schema_ids": [],
            "condition": {"op": "exists", "field": "payload.workflowId"},
            "dedup": {"fields": ["payload.workflowId"], "window_s": 300},
            "routing": {"recipients": [{"type": "on_call", "team_id": TEAM_ID}]},
            "presentation": {"title": "Failed", "severity": "critical", "colour": "red"},
            "runbook_id": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
    )
    return Match(event=EVENT, rule=rule, fingerprint=uuid.uuid4().hex)


def opened(match: Match) -> DedupOutcome:
    return Opened(
        alert_id=uuid.uuid7(), match=match, team_id=TEAM_ID, severity=Severity.CRITICAL, title="Failed", body=None
    )


def renotified(match: Match) -> DedupOutcome:
    return Renotified(
        alert_id=uuid.uuid7(),
        match=match,
        notification_seq=2,
        team_id=TEAM_ID,
        severity=Severity.CRITICAL,
        title="Failed",
        body=None,
    )


def repeated(match: Match) -> DedupOutcome:
    return Repeated(alert_id=uuid.uuid7(), match=match)


def key(match: Match) -> str:
    return dedup.window_key(match)


class NoSessions(async_sessionmaker[AsyncSession]):
    def __call__(self, **local_kw: object) -> AsyncSession:
        raise AssertionError("this event must not open a transaction")


class Calls:
    """Replaces the stage entrypoints the orchestrator reaches and records what they were called with.

    Each recorded match adds a team named after its window key in its savepoint, so a test can see which matches'
    database work committed.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, matches: list[Match]) -> None:
        self.recorded: list[Match] = []
        self.routed: list[Opened | Renotified] = []
        self.started: list[Opened] = []
        self.outcomes: dict[str, Callable[[Match], DedupOutcome]] = {}
        # What `record` and `route` raise per window key, after their database work.
        self.record_errors: dict[str, BaseException] = {}
        self.route_errors: dict[str, BaseException] = {}
        self.event_ids: list[object] = []

        async def normalise(raw: RawEvent, load_schemas: ingest.SchemaLoader) -> Event:
            return EVENT

        def evaluate(event: Event, rules: evaluation.RuleSet) -> list[Match]:
            return matches

        async def record(session: AsyncSession, match: Match, claim: dedup.Recordable) -> dedup.Recorded:
            session.add(Team(slug=f"t-{match.fingerprint[:20]}", name=claim.key))
            await session.flush()
            if error := self.record_errors.get(claim.key):
                raise error
            self.recorded.append(match)
            self.event_ids.append(structlog.contextvars.get_contextvars().get("event_id"))
            return dedup.Recorded(outcome=self.outcomes.get(claim.key, opened)(match), notified_at=NOW)

        async def route(session: AsyncSession, outcome: Opened | Renotified) -> list[uuid.UUID]:
            if error := self.route_errors.get(key(outcome.match)):
                raise error
            self.routed.append(outcome)
            return []

        async def start_run(session: AsyncSession, opened: Opened) -> uuid.UUID | None:
            self.started.append(opened)
            return None

        monkeypatch.setattr(ingest, "normalise", normalise)
        monkeypatch.setattr(evaluation, "evaluate", evaluate)
        monkeypatch.setattr(dedup, "record", record)
        monkeypatch.setattr(routing, "route", route)
        monkeypatch.setattr(executor, "start_run", start_run)


async def committed_teams(session: AsyncSession) -> set[str]:
    return set(await session.scalars(select(Team.name).where(Team.name.like("dedup:%"))))


def owned(match: Match) -> dedup.Ownership:
    return dedup.Ownership(key=key(match), token=dedup.pending_token(match))


async def test_a_new_alert_is_routed_its_runbook_started_and_its_window_confirmed(
    monkeypatch: pytest.MonkeyPatch, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    match = make_match()
    calls = Calls(monkeypatch, [match])
    windows = FakeWindows()

    result = await orchestrator.process_event(RAW, sessionmaker, no_schemas, RULES, windows)

    assert (result.event_id, result.matches) == (EVENT.event_id, 1)
    assert calls.recorded == [match]
    assert [o.match for o in calls.routed] == [match]
    assert [o.match for o in calls.started] == [match]
    assert [c.key for c in windows.confirmed] == [key(match)]
    assert windows.released == []


async def test_a_renotified_alert_is_routed_without_a_new_runbook_run(
    monkeypatch: pytest.MonkeyPatch, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    match = make_match()
    calls = Calls(monkeypatch, [match])
    calls.outcomes[key(match)] = renotified

    await orchestrator.process_event(RAW, sessionmaker, no_schemas, RULES, FakeWindows())

    assert [type(o) for o in calls.routed] == [Renotified]
    assert calls.started == []


async def test_a_repeat_recorded_in_postgres_is_neither_routed_nor_run(
    monkeypatch: pytest.MonkeyPatch, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    match = make_match()
    calls = Calls(monkeypatch, [match])
    calls.outcomes[key(match)] = repeated
    windows = FakeWindows({key(match): dedup.Pending(key=key(match))})

    await orchestrator.process_event(RAW, sessionmaker, no_schemas, RULES, windows)

    assert calls.recorded == [match]
    assert (calls.routed, calls.started) == ([], [])


async def test_a_held_window_is_counted_by_the_claim_without_a_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    match = make_match()
    calls = Calls(monkeypatch, [match])
    windows = FakeWindows({key(match): dedup.Held(key=key(match), alert_id=uuid.uuid7())})

    with structlog.testing.capture_logs() as logs:
        await orchestrator.process_event(RAW, NoSessions(), no_schemas, RULES, windows)

    assert calls.recorded == []
    assert (windows.confirmed, windows.released) == ([], [])
    [processed] = [entry for entry in logs if entry["event"] == "pipeline.event_processed"]
    assert [o["outcome"] for o in processed["outcomes"]] == ["repeated"]


@pytest.mark.parametrize("failing_stage", ["record", "route"])
async def test_a_failing_match_rolls_back_alone_and_the_others_commit(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    failing_stage: str,
) -> None:
    good, bad, also_good = make_match(), make_match(), make_match()
    calls = Calls(monkeypatch, [good, bad, also_good])
    errors = calls.record_errors if failing_stage == "record" else calls.route_errors
    errors[key(bad)] = RuntimeError("bad template")
    windows = FakeWindows()

    with structlog.testing.capture_logs() as logs:
        result = await orchestrator.process_event(RAW, sessionmaker, no_schemas, RULES, windows)

    assert result.matches == 3
    assert {o.match.fingerprint for o in calls.routed} == {good.fingerprint, also_good.fingerprint}
    assert await committed_teams(session) == {key(good), key(also_good)}
    assert {c.key for c in windows.confirmed} == {key(good), key(also_good)}
    assert windows.released == [owned(bad)]
    [failed] = [entry for entry in logs if entry["event"] == "pipeline.match_failed"]
    assert failed["rule_id"] == str(bad.rule.id)
    [processed] = [entry for entry in logs if entry["event"] == "pipeline.event_processed"]
    assert processed["failed_rule_ids"] == [str(bad.rule.id)]


async def test_a_cancellation_aborts_the_whole_event_and_releases_every_claim(
    monkeypatch: pytest.MonkeyPatch, session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    first, second = make_match(), make_match()
    calls = Calls(monkeypatch, [first, second])
    calls.record_errors[key(second)] = asyncio.CancelledError()
    calls.record_errors[key(first)] = asyncio.CancelledError()
    windows = FakeWindows()

    with pytest.raises(asyncio.CancelledError):
        await orchestrator.process_event(RAW, sessionmaker, no_schemas, RULES, windows)

    assert windows.confirmed == []
    assert {o.key for o in windows.released} == {key(first), key(second)}
    assert await committed_teams(session) == set()


async def test_a_failure_while_claiming_releases_the_events_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = make_match(), make_match()
    Calls(monkeypatch, [first, second])
    windows = FakeWindows(claim_error=RuntimeError("bug"))

    with pytest.raises(RuntimeError, match="bug"):
        await orchestrator.process_event(RAW, NoSessions(), no_schemas, RULES, windows)

    assert windows.released == [owned(first), owned(second)]


async def test_the_event_id_is_bound_to_the_log_context_while_the_event_is_processed(
    monkeypatch: pytest.MonkeyPatch, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    match = make_match()
    calls = Calls(monkeypatch, [match])

    with structlog.testing.capture_logs() as logs:
        await orchestrator.process_event(RAW, sessionmaker, no_schemas, RULES, FakeWindows())

    assert calls.event_ids == [str(EVENT.event_id)]
    assert "event_id" not in structlog.contextvars.get_contextvars()
    [processed] = [entry for entry in logs if entry["event"] == "pipeline.event_processed"]
    assert (processed["schema"], processed["rule_ids"]) == ("payment", [str(match.rule.id)])
    assert processed["outcomes"] == [
        {"rule_id": str(match.rule.id), "alert_id": str(calls.routed[0].alert_id), "outcome": "opened"}
    ]


async def test_an_event_without_matches_touches_no_window(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch, [])
    windows = FakeWindows()

    result = await orchestrator.process_event(RAW, NoSessions(), no_schemas, RULES, windows)

    assert result.matches == 0
    assert (calls.recorded, windows.claimed, windows.confirmed, windows.released) == ([], [], [], [])
