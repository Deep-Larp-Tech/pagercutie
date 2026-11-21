import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import AlertChanges
from tests.integration.pipeline.test_executor_loop import (
    NOW,
    PAST,
    FakeHttp,
    audit,
    claim,
    make_run,
    rows,
    set_step,
)

from pagercutie.alerts.models import Alert, StepRun
from pagercutie.alerts.schemas import StepStatus
from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction
from pagercutie.pipeline.executor import worker
from pagercutie.pipeline.executor.actions import Integrations, SimulatedOps
from pagercutie.pipeline.executor.outcomes import RetryFailed, RetryWatched, StepFailed, StepSucceeded
from pagercutie.pipeline.executor.stage import WATCH_INTERVAL, complete_step
from pagercutie.runbooks.steps import Escalate, HttpGet, RetryWorkflow, Step, StepGuard
from pagercutie.teams.models import Team

pytestmark = pytest.mark.anyio

RETRY_STEPS: list[Step] = [
    HttpGet(action="http_get", url="http://counterparty-service/health"),
    RetryWorkflow(action="retry_workflow", workflowId="{{workflowId}}", approval="none"),
    Escalate(
        action="escalate", team="counterparty-support", if_=StepGuard(step=1, failures_gte=2), approval="required"
    ),
]


@pytest.fixture
async def team(session: AsyncSession) -> Team:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    return team


async def watched_run(session: AsyncSession, team: Team, occurrences: int = 1) -> tuple[uuid.UUID, uuid.UUID]:
    """A run whose retry (step 1) succeeded once, with the baseline at the alert's current count."""
    run_id, alert_id, _ = await make_run(session, team, RETRY_STEPS)
    await set_step(session, run_id, 0, status=StepStatus.SUCCEEDED)
    await set_step(session, run_id, 1, status=StepStatus.SUCCEEDED, attempts=1, occurrences_at_run=occurrences)
    return run_id, alert_id


async def test_the_first_success_stores_the_baseline_and_watches(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team, RETRY_STEPS)
    await set_step(session, run_id, 0, status=StepStatus.SUCCEEDED)
    job = await claim(session, run_id, 1)

    await complete_step(session, job, StepSucceeded("accepted"), NOW)

    retry = (await rows(session, run_id))[1]
    assert (retry.status, retry.attempts, retry.failures) == (StepStatus.SUCCEEDED, 1, 0)
    assert (retry.occurrences_at_run, retry.run_at) == (1, NOW + WATCH_INTERVAL)
    assert [action for action, _ in await audit(session, run_id)] == [AuditAction.STEP_SUCCEEDED]


async def test_watching_goes_on_while_a_later_step_is_unfinished(session: AsyncSession, team: Team) -> None:
    run_id, _ = await watched_run(session, team)
    job = await claim(session, run_id, 1)

    await complete_step(session, job, RetryWatched(), NOW)

    retry, escalate = (await rows(session, run_id))[1:]
    assert (retry.status, retry.attempts, retry.run_at) == (StepStatus.SUCCEEDED, 1, NOW + WATCH_INTERVAL)
    assert escalate.run_at is None
    assert await audit(session, run_id) == []


async def test_a_watched_retry_announces_nothing(
    session: AsyncSession, team: Team, alert_changes: AlertChanges
) -> None:
    run_id, _ = await watched_run(session, team)
    job = await claim(session, run_id, 1)
    alert_changes.clear()

    await complete_step(session, job, RetryWatched(), NOW)

    assert alert_changes == []


async def test_watching_stops_when_every_step_is_finished(session: AsyncSession, team: Team) -> None:
    run_id, _ = await watched_run(session, team)
    await set_step(session, run_id, 2, status=StepStatus.SKIPPED)
    job = await claim(session, run_id, 1)

    await complete_step(session, job, RetryWatched(), NOW)

    assert (await rows(session, run_id))[1].run_at is None
    assert await audit(session, run_id) == []


async def test_a_failed_retry_is_counted_and_the_guarded_step_is_scheduled(session: AsyncSession, team: Team) -> None:
    run_id, _ = await watched_run(session, team)
    await set_step(session, run_id, 1, result="accepted")
    await session.execute(update(Alert).values(occurrences=2))
    job = await claim(session, run_id, 1)

    await complete_step(session, job, RetryFailed(StepSucceeded("accepted again")), NOW)

    retry, escalate = (await rows(session, run_id))[1:]
    assert (retry.status, retry.attempts, retry.failures, retry.result) == (
        StepStatus.SUCCEEDED,
        2,
        1,
        "accepted again",
    )
    assert (retry.occurrences_at_run, retry.run_at) == (2, NOW + WATCH_INTERVAL)
    assert escalate.run_at == NOW
    assert await audit(session, run_id) == [
        (AuditAction.STEP_RETRY_FAILED, {"index": 1, "status": "succeeded", "result": "accepted again", "failures": 1})
    ]


async def test_a_failed_rerun_ends_the_retry_failed_with_two_failures(session: AsyncSession, team: Team) -> None:
    run_id, _ = await watched_run(session, team)
    await session.execute(update(Alert).values(occurrences=2))
    job = await claim(session, run_id, 1)

    await complete_step(session, job, RetryFailed(StepFailed("engine down")), NOW)

    retry, escalate = (await rows(session, run_id))[1:]
    assert (retry.status, retry.attempts, retry.failures, retry.result) == (StepStatus.FAILED, 2, 2, "engine down")
    assert (retry.occurrences_at_run, retry.run_at) == (1, None)
    assert escalate.run_at == NOW
    assert await audit(session, run_id) == [
        (AuditAction.STEP_FAILED, {"index": 1, "status": "failed", "result": "engine down"})
    ]


async def test_a_failed_retry_of_a_finished_run_does_not_audit_the_finish_again(
    session: AsyncSession, team: Team
) -> None:
    run_id, _ = await watched_run(session, team)
    await set_step(session, run_id, 2, status=StepStatus.SKIPPED)
    await session.execute(update(Alert).values(occurrences=2))
    job = await claim(session, run_id, 1)

    await complete_step(session, job, RetryFailed(StepSucceeded("again")), NOW)

    assert [action for action, _ in await audit(session, run_id)] == [AuditAction.STEP_RETRY_FAILED]


async def test_the_settlement_runbook_escalates_after_the_retry_fails_twice(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], team: Team
) -> None:
    run_id, alert_id, _ = await make_run(session, team, RETRY_STEPS)
    http = FakeHttp()
    integrations = Integrations(http=http, ops=SimulatedOps())
    # The worker completes with the real clock, so claiming at NOW (an hour ahead) finds every `run_at`.
    assert datetime.now(UTC) + WATCH_INTERVAL + timedelta(minutes=1) < NOW

    async def pass_only(index: int) -> None:
        """One loop pass over step `index` alone: the test harness shares one connection, so passes cannot overlap."""
        await session.execute(update(StepRun).where(StepRun.run_id == run_id).values(run_at=None))
        await set_step(session, run_id, index, run_at=PAST)
        assert await worker.process_due(sessionmaker, integrations, NOW) == 1

    async def occurrence() -> None:
        await session.execute(update(Alert).where(Alert.id == alert_id).values(occurrences=Alert.occurrences + 1))

    # Step 1: start_run made http_get due; it succeeds and schedules the retry.
    assert await worker.process_due(sessionmaker, integrations, NOW) == 1
    check, retry, escalate = await rows(session, run_id)
    assert http.calls == ["http://counterparty-service/health"]
    assert (check.status, check.attempts) == (StepStatus.SUCCEEDED, 1)
    assert retry.run_at is not None

    # Step 2: the retry runs (attempt 1) and stores the baseline; the guarded escalate is scheduled, then stays pending.
    await pass_only(1)
    _, retry, escalate = await rows(session, run_id)
    assert (retry.status, retry.attempts, retry.failures, retry.occurrences_at_run) == (StepStatus.SUCCEEDED, 1, 0, 1)
    assert escalate.run_at is not None
    await pass_only(2)
    _, retry, escalate = await rows(session, run_id)
    assert (escalate.status, escalate.run_at) == (StepStatus.PENDING, None)

    # Nothing repeated: watching changes nothing.
    await pass_only(1)
    _, retry, escalate = await rows(session, run_id)
    assert (retry.attempts, retry.failures, escalate.status) == (1, 0, StepStatus.PENDING)

    # Step 3: one repeat is one failed retry; escalate is scheduled again and still waits.
    await occurrence()
    await pass_only(1)
    _, retry, escalate = await rows(session, run_id)
    assert (retry.status, retry.attempts, retry.failures, retry.occurrences_at_run) == (StepStatus.SUCCEEDED, 2, 1, 2)
    assert escalate.run_at is not None
    await pass_only(2)
    _, retry, escalate = await rows(session, run_id)
    assert (escalate.status, escalate.run_at) == (StepStatus.PENDING, None)

    # Step 4: the second repeat satisfies the guard.
    await occurrence()
    await pass_only(1)
    _, retry, escalate = await rows(session, run_id)
    assert (retry.attempts, retry.failures) == (3, 2)
    await pass_only(2)
    _, retry, escalate = await rows(session, run_id)
    assert (escalate.status, escalate.run_at) == (StepStatus.AWAITING_APPROVAL, None)

    entries = await session.scalars(
        select(AuditEntry)
        .where(
            AuditEntry.entity_id == alert_id,
            AuditEntry.action.not_in([AuditAction.ALERT_CREATED, AuditAction.RUNBOOK_RUN_STARTED]),
        )
        .order_by(AuditEntry.id)
    )
    assert [(entry.action, entry.data["index"]) for entry in entries] == [
        (AuditAction.STEP_SUCCEEDED, 0),
        (AuditAction.STEP_SUCCEEDED, 1),
        (AuditAction.STEP_RETRY_FAILED, 1),
        (AuditAction.STEP_RETRY_FAILED, 1),
        (AuditAction.STEP_AWAITING_APPROVAL, 2),
    ]
