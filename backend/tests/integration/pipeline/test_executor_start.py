import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.pipeline.test_dedup import WON, add_rule, make_match, make_rule

from pagercutie.alerts.models import RunbookRun, StepRun
from pagercutie.alerts.schemas import StepStatus
from pagercutie.audit.models import AuditEntry
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.executor.stage import start_run
from pagercutie.pipeline.messages import Opened
from pagercutie.rules import evaluator
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import Escalate, HttpGet, Manual, Step, StepGuard
from pagercutie.teams.models import Team

pytestmark = pytest.mark.anyio

STEPS: list[Step] = [
    HttpGet(action="http_get", url="https://status.example.com/{{workflowId}}"),
    Manual(action="manual", text="Check the dashboard"),
    Escalate(action="escalate", team="support", if_=StepGuard(step=0, failures_gte=2)),
]


@pytest.fixture
async def team(session: AsyncSession) -> Team:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    return team


@pytest.fixture
async def runbook(session: AsyncSession, team: Team) -> Runbook:
    runbook = Runbook(
        slug="retry", title="Retry", team_id=team.id, format=RunbookFormat.STRUCTURED, original="", steps=STEPS
    )
    session.add(runbook)
    await session.flush()
    return runbook


async def open_alert(session: AsyncSession, team: Team, runbook_id: uuid.UUID | None) -> Opened:
    """Opens the alert with `dedup.record`, so the alert row, its team and the event view are the real ones."""
    rule = make_rule(team)
    rule.runbook_id = runbook_id
    outcome = await dedup.record(session, make_match(await add_rule(session, rule), team), WON)
    assert isinstance(outcome, Opened)
    return outcome


async def step_runs(session: AsyncSession, run_id: uuid.UUID) -> list[StepRun]:
    return list(await session.scalars(select(StepRun).where(StepRun.run_id == run_id).order_by(StepRun.index)))


async def count(session: AsyncSession, model: type[RunbookRun] | type[AuditEntry]) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_a_run_starts_with_one_pending_step_run_per_step(
    session: AsyncSession, team: Team, runbook: Runbook
) -> None:
    opened = await open_alert(session, team, runbook.id)

    run_id = await start_run(session, opened)

    assert run_id is not None
    run = await session.get_one(RunbookRun, run_id, populate_existing=True)
    event = opened.match.event
    assert run.event == evaluator.event_view(
        source=event.source, schema_id=event.schema_id, severity=event.severity, payload=event.payload
    )
    assert (run.alert_id, run.runbook_id) == (opened.alert_id, runbook.id)
    steps = await step_runs(session, run_id)
    assert [s.step for s in steps] == STEPS
    assert [s.index for s in steps] == [0, 1, 2]
    assert {(s.status, s.attempts, s.failures) for s in steps} == {(StepStatus.PENDING, 0, 0)}
    assert steps[0].run_at is not None
    assert [s.run_at for s in steps[1:]] == [None, None]
    first = steps[0].step
    assert isinstance(first, HttpGet)
    assert first.url == "https://status.example.com/{{workflowId}}"


async def test_the_start_is_audited_as_the_system_in_the_alerts_team(
    session: AsyncSession, team: Team, runbook: Runbook
) -> None:
    opened = await open_alert(session, team, runbook.id)

    run_id = await start_run(session, opened)

    entry = await session.scalar(select(AuditEntry).where(AuditEntry.entity_type == "runbook_run"))
    assert entry is not None
    assert (entry.actor_user_id, entry.action, entry.entity_id, entry.team_id) == (
        None,
        "runbook_run.started",
        run_id,
        team.id,
    )
    assert entry.data == {"alert_id": str(opened.alert_id), "runbook_id": str(runbook.id), "steps": 3}


async def test_a_rule_without_a_runbook_starts_no_run(session: AsyncSession, team: Team) -> None:
    opened = await open_alert(session, team, None)

    assert await start_run(session, opened) is None
    assert await count(session, RunbookRun) == 0
    assert await count(session, AuditEntry) == 0


async def test_a_missing_runbook_starts_no_run(session: AsyncSession, team: Team) -> None:
    opened = await open_alert(session, team, None)
    stale = opened.match.rule.model_copy(update={"runbook_id": uuid.uuid7()})
    opened = Opened(alert_id=opened.alert_id, match=opened.match.model_copy(update={"rule": stale}))

    assert await start_run(session, opened) is None
    assert await count(session, RunbookRun) == 0
    assert await count(session, AuditEntry) == 0


async def test_a_runbook_without_steps_starts_no_run(session: AsyncSession, team: Team) -> None:
    empty = Runbook(slug="empty", title="Empty", team_id=team.id, format=RunbookFormat.TEXT, original="", steps=[])
    session.add(empty)
    await session.flush()
    opened = await open_alert(session, team, empty.id)

    assert await start_run(session, opened) is None
    assert await count(session, RunbookRun) == 0


async def test_starting_twice_returns_the_same_run_and_changes_nothing(
    session: AsyncSession, team: Team, runbook: Runbook
) -> None:
    opened = await open_alert(session, team, runbook.id)
    first = await start_run(session, opened)

    runbook.steps = STEPS[:1]
    await session.flush()
    second = await start_run(session, opened)

    assert first is not None
    assert second == first
    assert await count(session, RunbookRun) == 1
    assert len(await step_runs(session, first)) == 3
    assert await count(session, AuditEntry) == 1


async def test_editing_the_runbook_does_not_change_a_started_run(
    session: AsyncSession, team: Team, runbook: Runbook
) -> None:
    opened = await open_alert(session, team, runbook.id)
    run_id = await start_run(session, opened)
    assert run_id is not None

    runbook.steps = [Manual(action="manual", text="Different")]
    await session.flush()

    steps = await step_runs(session, run_id)
    for step in steps:
        await session.refresh(step)
    assert [s.step for s in steps] == STEPS
