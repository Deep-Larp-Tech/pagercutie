import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from pydantic import JsonValue
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from tests.conftest import AlertChanges
from tests.integration.pipeline.test_dedup import FINGERPRINT, WON, add_rule, make_match, make_rule
from tests.integration.pipeline.test_executor_start import STEPS

from pagercutie.alerts.models import Alert, RunbookRun, StepRun
from pagercutie.alerts.schemas import AlertStatus, Resolution, StepStatus
from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction, AuditEntityType
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.executor import worker
from pagercutie.pipeline.executor.actions import HttpResult, Integrations, SimulatedOps
from pagercutie.pipeline.executor.outcomes import (
    AwaitingAnswer,
    AwaitingApproval,
    AwaitingManual,
    GuardPending,
    StepFailed,
    StepOutcome,
    StepSucceeded,
    WaitScheduled,
)
from pagercutie.pipeline.executor.perform import Settle
from pagercutie.pipeline.executor.stage import StepJob, claim_due_steps, complete_step, plan_step, start_run
from pagercutie.pipeline.executor.worker import ExecutorConfig
from pagercutie.pipeline.messages import Opened
from pagercutie.rules.models import Rule
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import Step, Wait
from pagercutie.teams.models import Team

pytestmark = pytest.mark.anyio

NOW = datetime.now(UTC) + timedelta(hours=1)
PAST = NOW - timedelta(seconds=1)
LATER = NOW + timedelta(minutes=5)
LEASE = timedelta(seconds=30)
CONFIG = ExecutorConfig(lease=LEASE, step_timeout_seconds=20.0, max_errors=5)


def at_now() -> datetime:
    """The loop's clock in these tests: every `run_at` they set is before it."""
    return NOW


async def make_run(
    session: AsyncSession, team: Team, steps: Sequence[Step] = STEPS, fingerprint: str = FINGERPRINT
) -> tuple[uuid.UUID, uuid.UUID, Opened]:
    """Returns the run ID, the alert ID and the opened alert."""
    runbook = Runbook(
        slug=f"rb-{uuid.uuid4().hex[:8]}",
        title="Retry",
        team_id=team.id,
        format=RunbookFormat.STRUCTURED,
        original="",
        steps=list(steps),
    )
    session.add(runbook)
    rule = make_rule(team)
    await session.flush()
    rule.runbook_id = runbook.id
    opened = (
        await dedup.record(session, make_match(await add_rule(session, rule), team, fingerprint=fingerprint), WON)
    ).outcome
    assert isinstance(opened, Opened)
    run_id = await start_run(session, opened)
    assert run_id is not None
    return run_id, opened.alert_id, opened


@pytest.fixture
async def team(session: AsyncSession) -> Team:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    return team


async def rows(session: AsyncSession, run_id: uuid.UUID) -> list[StepRun]:
    return list(
        await session.scalars(
            select(StepRun)
            .where(StepRun.run_id == run_id)
            .order_by(StepRun.index)
            .execution_options(populate_existing=True)
        )
    )


async def set_step(session: AsyncSession, run_id: uuid.UUID, index: int, **values: object) -> None:
    await session.execute(update(StepRun).where(StepRun.run_id == run_id, StepRun.index == index).values(values))


async def audit(session: AsyncSession, run_id: uuid.UUID) -> list[tuple[AuditAction, dict[str, JsonValue]]]:
    """The run's audit entries after its start, without `run_id`, which every entry carries."""
    alert_id = await session.scalar(select(RunbookRun.alert_id).where(RunbookRun.id == run_id))
    entries = await session.scalars(
        select(AuditEntry)
        .where(
            AuditEntry.entity_id == alert_id,
            AuditEntry.action.not_in([AuditAction.ALERT_CREATED, AuditAction.RUNBOOK_RUN_STARTED]),
        )
        .order_by(AuditEntry.id)
    )
    result: list[tuple[AuditAction, dict[str, JsonValue]]] = []
    for entry in entries:
        assert entry.data["run_id"] == str(run_id)
        result.append((entry.action, {key: value for key, value in entry.data.items() if key != "run_id"}))
    return result


async def claim(session: AsyncSession, run_id: uuid.UUID, index: int) -> StepJob:
    """Makes step `index` the only due step of the run and claims it."""
    await session.execute(update(StepRun).where(StepRun.run_id == run_id).values(run_at=None))
    await set_step(session, run_id, index, run_at=PAST)
    (job,) = await claim_due_steps(session, 10, NOW, LEASE)
    assert job.index == index
    return job


async def test_due_steps_are_claimed_with_a_lease_and_keep_their_status(session: AsyncSession, team: Team) -> None:
    run_id, alert_id, _ = await make_run(session, team)
    await set_step(session, run_id, 1, failures=3)

    jobs = await claim_due_steps(session, 10, NOW, LEASE)

    assert [job.index for job in jobs] == [0]
    job = jobs[0]
    run = await session.get_one(RunbookRun, run_id, populate_existing=True)
    assert (job.run_id, job.alert_id, job.team_id) == (run_id, alert_id, team.id)
    assert (job.status, job.guard_answered, job.approved, job.attempts) == (StepStatus.PENDING, False, False, 0)
    assert (job.occurrences, job.event) == (1, run.event)
    assert dict(job.failures_by_index) == {0: 0, 1: 3, 2: 0}
    first = (await rows(session, run_id))[0]
    assert first.run_at is not None
    assert first.run_at < NOW
    assert (first.lease_until, first.status, first.errors) == (NOW + LEASE, StepStatus.PENDING, 0)
    assert job.unsettled == frozenset({0, 1, 2})


async def test_steps_not_due_are_not_claimed(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team)
    await set_step(session, run_id, 0, run_at=NOW + timedelta(seconds=1))

    assert await claim_due_steps(session, 10, NOW, LEASE) == []
    assert [s.run_at for s in (await rows(session, run_id))[1:]] == [None, None]


async def test_the_limit_and_the_order_follow_run_at(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team)
    await set_step(session, run_id, 0, run_at=NOW - timedelta(seconds=5))
    await set_step(session, run_id, 1, run_at=NOW - timedelta(seconds=9))

    assert [job.index for job in await claim_due_steps(session, 1, NOW, LEASE)] == [1]


async def test_steps_of_a_resolved_alert_are_not_claimed(session: AsyncSession, team: Team) -> None:
    run_id, alert_id, _ = await make_run(session, team)
    await session.execute(
        update(Alert)
        .where(Alert.id == alert_id)
        .values(status=AlertStatus.RESOLVED, resolved_at=NOW, resolution=Resolution.AUTO)
    )

    assert await claim_due_steps(session, 10, NOW, LEASE) == []
    assert (await rows(session, run_id))[0].run_at is None


async def test_an_expired_lease_is_claimed_again(session: AsyncSession, team: Team) -> None:
    await make_run(session, team)
    assert len(await claim_due_steps(session, 10, NOW, LEASE)) == 1

    assert await claim_due_steps(session, 10, NOW + LEASE - timedelta(seconds=1), LEASE) == []
    (job,) = await claim_due_steps(session, 10, NOW + LEASE, LEASE)
    # The first claim ended without an outcome (ADR-0106).
    assert job.errors == 1


@pytest.fixture
async def committed_run(engine: AsyncEngine) -> AsyncIterator[uuid.UUID]:
    """A run committed for real, so two connections can claim from it; removed afterwards."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        team = Team(slug=f"claim-{uuid.uuid7().hex[:8]}", name="Claim")
        session.add(team)
        await session.flush()
        run_id, alert_id, opened = await make_run(session, team)
        await set_step(session, run_id, 0, run_at=PAST)
        await set_step(session, run_id, 1, run_at=PAST)
        await session.commit()
    yield run_id
    async with AsyncSession(engine) as session, session.begin():
        rule_id = opened.match.rule.id
        runbook_id = (await session.get_one(RunbookRun, run_id)).runbook_id
        await session.execute(delete(AuditEntry).where(AuditEntry.team_id == team.id))
        await session.execute(delete(RunbookRun).where(RunbookRun.id == run_id))
        await session.execute(delete(Alert).where(Alert.id == alert_id))
        await session.execute(delete(Rule).where(Rule.id == rule_id))
        await session.execute(delete(Runbook).where(Runbook.id == runbook_id))
        await session.execute(delete(Team).where(Team.id == team.id))


async def test_concurrent_claims_get_disjoint_steps(engine: AsyncEngine, committed_run: uuid.UUID) -> None:
    async with AsyncSession(engine) as first, AsyncSession(engine) as second:
        await first.begin()
        held = await claim_due_steps(first, 1, NOW, LEASE)
        await second.begin()
        other = await claim_due_steps(second, 10, NOW, LEASE)
        await second.commit()
        await first.commit()

    assert [job.index for job in held] == [0]
    assert [job.index for job in other] == [1]
    assert {job.run_id for job in held + other} == {committed_run}


async def test_a_success_stores_the_result_and_schedules_the_next_step(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)

    await complete_step(session, job, StepSucceeded("HTTP 200 in 35 ms"), NOW)

    first, second, third = await rows(session, run_id)
    assert (first.status, first.attempts, first.failures, first.result, first.run_at) == (
        StepStatus.SUCCEEDED,
        1,
        0,
        "HTTP 200 in 35 ms",
        None,
    )
    assert second.run_at == NOW
    assert third.run_at is None
    assert await audit(session, run_id) == [
        (AuditAction.STEP_SUCCEEDED, {"index": 0, "status": "succeeded", "result": "HTTP 200 in 35 ms"})
    ]
    entry = await session.scalar(select(AuditEntry).where(AuditEntry.action == AuditAction.STEP_SUCCEEDED))
    assert entry is not None
    assert (entry.actor_user_id, entry.entity_type, entry.team_id) == (None, AuditEntityType.ALERT, team.id)


async def test_a_failure_counts_and_still_runs_the_next_step_in_order(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)

    await complete_step(session, job, StepFailed("HTTP 500 in 8 ms"), NOW)

    first, second, third = await rows(session, run_id)
    assert (first.status, first.attempts, first.failures, first.result, first.run_at) == (
        StepStatus.FAILED,
        1,
        1,
        "HTTP 500 in 8 ms",
        None,
    )
    assert second.run_at == NOW
    assert (third.status, third.run_at) == (StepStatus.PENDING, None)
    assert [action for action, _ in await audit(session, run_id)] == [AuditAction.STEP_FAILED]


async def test_the_guarded_step_is_scheduled_as_the_next_step_after_a_failure(
    session: AsyncSession, team: Team
) -> None:
    run_id, _, _ = await make_run(session, team)
    await set_step(session, run_id, 1, status=StepStatus.SUCCEEDED)
    job = await claim(session, run_id, 0)

    await complete_step(session, job, StepFailed("HTTP 500 in 8 ms"), NOW)

    assert (await rows(session, run_id))[2].run_at == NOW


async def test_the_finish_of_a_run_is_audited_on_the_alert(session: AsyncSession, team: Team) -> None:
    run_id, alert_id, _ = await make_run(session, team)
    await set_step(session, run_id, 0, status=StepStatus.SUCCEEDED)
    await set_step(session, run_id, 1, status=StepStatus.SKIPPED)
    job = await claim(session, run_id, 2)

    await complete_step(session, job, StepSucceeded("Escalated"), NOW)

    entry = await session.scalar(select(AuditEntry).where(AuditEntry.action == AuditAction.RUNBOOK_RUN_FINISHED))
    assert entry is not None
    assert (entry.entity_type, entry.entity_id, entry.actor_user_id, entry.team_id) == (
        AuditEntityType.ALERT,
        alert_id,
        None,
        team.id,
    )
    assert entry.data == {"run_id": str(run_id), "steps": 3}


async def test_the_last_step_finishing_finishes_the_run(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team)
    await set_step(session, run_id, 0, status=StepStatus.SUCCEEDED)
    await set_step(session, run_id, 1, status=StepStatus.SKIPPED)
    job = await claim(session, run_id, 2)

    await complete_step(session, job, StepSucceeded("Escalated"), NOW)

    assert [s.run_at for s in await rows(session, run_id)] == [None, None, None]
    actions = sorted(action for action, _ in await audit(session, run_id))
    assert actions == [AuditAction.RUNBOOK_RUN_FINISHED, AuditAction.STEP_SUCCEEDED]


@pytest.mark.parametrize(
    ("outcome", "status", "result"),
    [
        (AwaitingApproval(), StepStatus.AWAITING_APPROVAL, None),
        (AwaitingAnswer(question="Is it healthy?"), StepStatus.AWAITING_ANSWER, "Is it healthy?"),
        (AwaitingManual(), StepStatus.AWAITING_MANUAL, None),
    ],
)
async def test_a_step_awaiting_a_person_stops_the_run(
    session: AsyncSession, team: Team, outcome: StepOutcome, status: StepStatus, result: str | None
) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)

    await complete_step(session, job, outcome, NOW)

    assert [(s.status, s.attempts, s.result, s.run_at) for s in await rows(session, run_id)] == [
        (status, 0, result, None),
        (StepStatus.PENDING, 0, None, None),
        (StepStatus.PENDING, 0, None, None),
    ]
    assert await audit(session, run_id) == [
        (AuditAction(f"step.{status}"), {"index": 0, "status": status, "result": result})
    ]


async def test_a_pending_guard_waits_without_an_audit_entry(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 2)

    await complete_step(session, job, GuardPending(), NOW)

    last = (await rows(session, run_id))[2]
    assert (last.status, last.attempts, last.run_at) == (StepStatus.PENDING, 0, None)
    assert await audit(session, run_id) == []


async def test_starting_a_run_announces_the_alert(
    session: AsyncSession, team: Team, alert_changes: AlertChanges
) -> None:
    _, alert_id, _ = await make_run(session, team)

    assert alert_changes == [(alert_id, "alert.updated")]


@pytest.mark.parametrize(
    "outcome",
    [StepSucceeded("HTTP 200 in 35 ms"), StepFailed("HTTP 500 in 8 ms"), AwaitingApproval(), AwaitingManual()],
)
async def test_a_step_the_executor_moves_on_announces_the_alert(
    session: AsyncSession, team: Team, alert_changes: AlertChanges, outcome: StepOutcome
) -> None:
    run_id, alert_id, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)
    alert_changes.clear()

    await complete_step(session, job, outcome, NOW)

    assert alert_changes == [(alert_id, "alert.updated")]


async def test_a_pending_guard_announces_nothing(
    session: AsyncSession, team: Team, alert_changes: AlertChanges
) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 2)
    alert_changes.clear()

    await complete_step(session, job, GuardPending(), NOW)

    assert alert_changes == []


async def test_a_dropped_outcome_announces_nothing(
    session: AsyncSession, team: Team, alert_changes: AlertChanges
) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)
    await set_step(session, run_id, 0, lease_until=LATER)
    alert_changes.clear()

    await complete_step(session, job, StepSucceeded("HTTP 200 in 35 ms"), NOW)

    assert alert_changes == []


async def test_a_wait_comes_due_after_its_delay(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)

    await complete_step(session, job, WaitScheduled(30), NOW)

    first, second, _ = await rows(session, run_id)
    assert (first.status, first.attempts, first.result, first.run_at) == (
        StepStatus.RUNNING,
        1,
        "Waiting 30 s",
        NOW + timedelta(seconds=30),
    )
    assert second.run_at is None
    assert await audit(session, run_id) == [
        (AuditAction.STEP_STARTED, {"index": 0, "status": "running", "result": "Waiting 30 s"})
    ]


async def test_an_outcome_is_dropped_when_an_approval_arrived_during_the_step(
    session: AsyncSession, team: Team
) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)
    await set_step(session, run_id, 0, approved=True, run_at=NOW)

    await complete_step(session, job, StepSucceeded("HTTP 200"), NOW + timedelta(seconds=1))

    first, second, _ = await rows(session, run_id)
    assert (first.status, first.attempts, first.result, first.run_at) == (StepStatus.PENDING, 0, None, NOW)
    assert first.approved
    assert second.run_at is None
    assert await audit(session, run_id) == []


async def test_an_outcome_is_dropped_when_only_a_gate_flag_or_the_status_changed(
    session: AsyncSession, team: Team
) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)
    await set_step(session, run_id, 0, guard_answered=True, run_at=job.lease)

    await complete_step(session, job, StepSucceeded("HTTP 200"), NOW + timedelta(seconds=1))
    await set_step(session, run_id, 0, guard_answered=False, status=StepStatus.AWAITING_ANSWER)
    await complete_step(session, job, StepSucceeded("HTTP 200"), NOW + timedelta(seconds=1))

    first = (await rows(session, run_id))[0]
    assert (first.status, first.attempts, first.result) == (StepStatus.AWAITING_ANSWER, 0, None)
    assert await audit(session, run_id) == []


async def test_an_outcome_is_dropped_when_the_lease_was_taken_over(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)
    taken = NOW + timedelta(seconds=45)
    await set_step(session, run_id, 0, lease_until=taken)

    await complete_step(session, job, StepSucceeded("HTTP 200"), NOW + timedelta(seconds=40))

    first, second, _ = await rows(session, run_id)
    assert (first.status, first.attempts, first.result, first.lease_until) == (StepStatus.PENDING, 0, None, taken)
    assert second.run_at is None
    assert await audit(session, run_id) == []


async def test_completing_the_same_claim_twice_writes_once(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team)
    job = await claim(session, run_id, 0)

    await complete_step(session, job, WaitScheduled(30), NOW)
    await complete_step(session, job, WaitScheduled(30), NOW)

    first = (await rows(session, run_id))[0]
    assert (first.status, first.attempts) == (StepStatus.RUNNING, 1)
    assert len(await audit(session, run_id)) == 1


async def test_a_wait_behind_the_approval_gate_finishes_after_its_delay(session: AsyncSession, team: Team) -> None:
    steps: list[Step] = [Wait(action="wait", seconds=30, approval="required")]
    run_id, _, _ = await make_run(session, team, steps)
    await set_step(session, run_id, 0, approved=True)

    job = await claim(session, run_id, 0)
    assert plan_step(job, CONFIG.max_errors) == Settle(WaitScheduled(30))
    await complete_step(session, job, WaitScheduled(30), NOW)
    assert (await rows(session, run_id))[0].status is StepStatus.RUNNING

    (job,) = await claim_due_steps(session, 10, NOW + timedelta(seconds=31), LEASE)

    assert plan_step(job, CONFIG.max_errors) == Settle(StepSucceeded("Waited 30 s"))
    assert job.errors == 0


class FakeHttp:
    def __init__(self, status: int = 200, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.calls: list[str] = []
        self.keys: list[uuid.UUID] = []

    async def request(
        self, method: Literal["GET", "POST", "PUT"], url: str, json: JsonValue | None, idempotency_key: uuid.UUID
    ) -> HttpResult:
        self.calls.append(url)
        self.keys.append(idempotency_key)
        if self.error is not None:
            raise self.error
        return HttpResult(status=self.status, elapsed_ms=5)


async def test_process_due_runs_a_step_and_schedules_the_next(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], team: Team
) -> None:
    run_id, _, _ = await make_run(session, team)
    http = FakeHttp()

    claimed = await worker.process_due(sessionmaker, Integrations(http=http, ops=SimulatedOps()), CONFIG, at_now)

    assert claimed == 1
    assert http.calls == ["https://status.example.com/wf-1"]
    first, second, _ = await rows(session, run_id)
    assert (first.status, first.attempts, first.run_at, first.lease_until) == (StepStatus.SUCCEEDED, 1, None, None)
    assert first.result is not None
    assert first.result.startswith("HTTP 200")
    assert http.keys == [first.attempt_key]
    assert first.acted_at == NOW
    assert second.run_at == NOW
    assert [(action, data["status"]) for action, data in await audit(session, run_id)] == [
        (AuditAction.STEP_STARTED, "running"),
        (AuditAction.STEP_SUCCEEDED, "succeeded"),
    ]


async def test_a_step_whose_integration_raises_keeps_its_lease_and_running_status(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], team: Team
) -> None:
    run_id, _, _ = await make_run(session, team)
    integrations = Integrations(http=FakeHttp(error=RuntimeError("boom")), ops=SimulatedOps())

    assert await worker.process_due(sessionmaker, integrations, CONFIG, at_now) == 1

    first, second, _ = await rows(session, run_id)
    assert (first.status, first.attempts, first.errors, first.lease_until) == (StepStatus.RUNNING, 0, 0, NOW + LEASE)
    assert first.attempt_key is not None
    assert second.run_at is None
    assert [action for action, _ in await audit(session, run_id)] == [AuditAction.STEP_STARTED]


async def test_the_loop_returns_when_it_is_stopping(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    wake = asyncio.Event()
    stopping = asyncio.Event()
    loop = worker.executor_loop(sessionmaker, Integrations(http=FakeHttp(), ops=SimulatedOps()), wake, CONFIG)
    task = asyncio.ensure_future(loop(stopping))
    await asyncio.sleep(0.05)
    assert not task.done()

    stopping.set()
    await asyncio.wait_for(task, 1)


async def test_the_steps_pending_handler_wakes_the_loop() -> None:
    wake = asyncio.Event()

    await worker.steps_pending_handler(wake)()

    assert wake.is_set()
