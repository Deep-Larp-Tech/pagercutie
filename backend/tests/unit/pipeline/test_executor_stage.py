import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pagercutie.alerts.runs import FINAL_STEP_STATUSES, is_final
from pagercutie.alerts.schemas import StepStatus
from pagercutie.audit.schemas import AuditAction
from pagercutie.pipeline.executor.outcomes import (
    AwaitingAnswer,
    GaveUp,
    GuardPending,
    GuardSkipped,
    ResolvedOutcome,
    RetryFailed,
    RetryWatched,
    StepFailed,
    StepSucceeded,
    StepTimedOut,
    WaitScheduled,
)
from pagercutie.pipeline.executor.stage import StepJob
from pagercutie.pipeline.executor.transitions import (
    WATCH_INTERVAL,
    Await,
    Delay,
    Finish,
    Hold,
    Watch,
    executed_action,
    transition,
)
from pagercutie.runbooks.steps import HttpGet, RetryWorkflow, Step, Wait

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
KEY = uuid.UUID("0193e4b0-0000-7000-8000-000000000001")
HTTP = HttpGet(action="http_get", url="http://x")
RETRY = RetryWorkflow(action="retry_workflow", workflowId="wf-1")


def job(
    step: Step = HTTP,
    status: StepStatus = StepStatus.RUNNING,
    failures_by_index: dict[int, int] | None = None,
    unsettled: frozenset[int] = frozenset(),
    attempt_key: uuid.UUID | None = KEY,
) -> StepJob:
    return StepJob(
        run_id=uuid.uuid4(),
        index=1,
        alert_id=uuid.uuid4(),
        team_id=None,
        step=step,
        status=status,
        guard_answered=False,
        approved=False,
        decided_by=None,
        attempts=0,
        errors=0,
        failures_by_index=failures_by_index or {},
        unsettled=unsettled,
        occurrences=4,
        last_seen_at=NOW,
        occurrences_at_run=None,
        attempt_key=attempt_key,
        acted_at=NOW,
        event={},
        due_at=NOW,
        lease=NOW,
        traceparent=None,
    )


def test_failures_reads_the_mapped_count_and_is_zero_for_a_missing_index() -> None:
    state = job(failures_by_index={0: 2})

    assert state.failures(0) == 2
    assert state.failures(1) == 0


def test_can_still_fail_reads_the_unsettled_steps() -> None:
    state = job(unsettled=frozenset({0}))

    assert state.can_still_fail(0)
    assert not state.can_still_fail(2)


def test_final_statuses_are_succeeded_failed_and_skipped() -> None:
    final = {StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED}
    assert final == FINAL_STEP_STATUSES
    assert {status for status in StepStatus if is_final(status)} == final


@pytest.mark.parametrize(
    ("step", "outcome", "expected"),
    [
        (HTTP, StepSucceeded("ok"), Finish(StepStatus.SUCCEEDED, "ok", AuditAction.STEP_SUCCEEDED, attempted=True)),
        (
            RETRY,
            StepSucceeded("ok"),
            Finish(
                StepStatus.SUCCEEDED,
                "ok",
                AuditAction.STEP_SUCCEEDED,
                attempted=True,
                baseline=4,
                watch_at=NOW + WATCH_INTERVAL,
            ),
        ),
        (
            HTTP,
            StepFailed("500"),
            Finish(StepStatus.FAILED, "500", AuditAction.STEP_FAILED, attempted=True, failures_added=1),
        ),
        (
            HTTP,
            StepTimedOut(20.0),
            Finish(
                StepStatus.FAILED,
                "Timed out after 20 s",
                AuditAction.STEP_FAILED,
                attempted=True,
                failures_added=1,
                details={"reason": "timed_out"},
            ),
        ),
        (
            HTTP,
            GaveUp(5),
            Finish(
                StepStatus.FAILED,
                "Gave up after 5 attempts that ended without an outcome",
                AuditAction.STEP_FAILED,
                attempted=False,
                failures_added=1,
                details={"reason": "errors", "errors": 5},
            ),
        ),
        (
            HTTP,
            GuardSkipped("not met"),
            Finish(
                StepStatus.SKIPPED,
                "not met",
                AuditAction.STEP_SKIPPED,
                attempted=False,
                details={"reason": "guard_false"},
            ),
        ),
        (
            RETRY,
            RetryFailed(StepSucceeded("again")),
            Finish(
                StepStatus.SUCCEEDED,
                "again",
                AuditAction.STEP_RETRY_FAILED,
                attempted=True,
                failures_added=1,
                baseline=4,
                watch_at=NOW + WATCH_INTERVAL,
                details={"failures": 1},
            ),
        ),
        (
            RETRY,
            RetryFailed(StepFailed("down")),
            Finish(StepStatus.FAILED, "down", AuditAction.STEP_FAILED, attempted=True, failures_added=2),
        ),
        (RETRY, RetryWatched(baseline=6), Watch(baseline=6)),
        (HTTP, AwaitingAnswer("q"), Await(StepStatus.AWAITING_ANSWER, "q")),
        (HTTP, GuardPending(), Hold()),
        (Wait(action="wait", seconds=30), WaitScheduled(30), Delay(NOW + timedelta(seconds=30), "Waiting 30 s")),
    ],
)
def test_each_outcome_maps_to_one_transition(step: Step, outcome: ResolvedOutcome, expected: object) -> None:
    assert transition(job(step), outcome, NOW) == expected


def test_only_an_action_that_ran_counts_as_executed() -> None:
    assert executed_action(job(), StepSucceeded("ok"))
    assert executed_action(job(RETRY), RetryFailed(StepTimedOut(1.0)))
    assert not executed_action(job(attempt_key=None), StepSucceeded("Waited 5 s"))
    assert not executed_action(job(status=StepStatus.PENDING), GuardSkipped("not met"))
    assert not executed_action(job(), GaveUp(5))
