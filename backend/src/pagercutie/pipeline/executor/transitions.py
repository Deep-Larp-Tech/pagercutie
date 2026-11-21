"""The step run's next state for each outcome (SPEC §11.3). Pure: `completion.complete_step` writes the result."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, assert_never

from pydantic import JsonValue

from pagercutie.alerts.schemas import StepStatus
from pagercutie.audit.schemas import AuditAction
from pagercutie.pipeline.executor.claims import StepJob
from pagercutie.pipeline.executor.outcomes import (
    ActionResult,
    AwaitingAnswer,
    AwaitingApproval,
    AwaitingManual,
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
from pagercutie.runbooks.steps import RetryWorkflow

# How often a succeeded retry checks the alert's occurrences. The counter flush adds up to 5 s before a repeat shows in
# `alerts.occurrences` (SPEC §5.2).
WATCH_INTERVAL = timedelta(seconds=5)

type FinalStatus = Literal[StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED]
type WaitingStatus = Literal[StepStatus.AWAITING_APPROVAL, StepStatus.AWAITING_ANSWER, StepStatus.AWAITING_MANUAL]


@dataclass(frozen=True)
class Finish:
    """The step reaches a final status, is audited, and the run moves on."""

    status: FinalStatus
    result: str
    audit: AuditAction
    # The action ran, so `attempts` goes up by one.
    attempted: bool
    # Added to `failures`: 1 for a failed step or a detected failed retry, 2 when the re-run failed too.
    failures_added: int = 0
    # A succeeded retry's new `occurrences_at_run`, and when it is claimed again to watch for repeats (SPEC §11.4).
    baseline: int | None = None
    watch_at: datetime | None = None
    # Added to the audit entry's data, e.g. the reason for a skip.
    details: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class Await:
    """The step waits for a person; audited when the status changes."""

    status: WaitingStatus
    # The guard's question for `awaiting_answer`; null keeps `result`.
    result: str | None


@dataclass(frozen=True)
class Hold:
    """The guard's answer is not known yet: the step stays `pending` with `run_at` null and is not audited."""


@dataclass(frozen=True)
class Delay:
    """A `wait` step is `running` until `until`, then finishes on its next claim."""

    until: datetime
    result: str


@dataclass(frozen=True)
class Watch:
    """A succeeded retry saw no failure: it stays `succeeded` and is checked again while the run is unfinished."""

    # The new `occurrences_at_run`; null keeps it.
    baseline: int | None


type Transition = Finish | Await | Hold | Delay | Watch
"""The step run's next state."""


def transition(job: StepJob, outcome: ResolvedOutcome, now: datetime) -> Transition:
    """Map `outcome` of the claimed `job` to the step run's next state."""
    match outcome:
        case StepSucceeded(result=result):
            if isinstance(job.step, RetryWorkflow):
                # It stays claimable so its next claim can see a repeat occurrence (SPEC §11.4).
                return Finish(
                    StepStatus.SUCCEEDED,
                    result,
                    AuditAction.STEP_SUCCEEDED,
                    attempted=True,
                    baseline=job.occurrences,
                    watch_at=now + WATCH_INTERVAL,
                )
            return Finish(StepStatus.SUCCEEDED, result, AuditAction.STEP_SUCCEEDED, attempted=True)
        case StepFailed() | StepTimedOut():
            return _failed(outcome, failures_added=1)
        case GaveUp(errors=errors):
            return Finish(
                StepStatus.FAILED,
                f"Gave up after {errors} attempts that ended without an outcome",
                AuditAction.STEP_FAILED,
                attempted=False,
                failures_added=1,
                details={"reason": "errors", "errors": errors},
            )
        case GuardSkipped(reason=reason):
            return Finish(
                StepStatus.SKIPPED, reason, AuditAction.STEP_SKIPPED, attempted=False, details={"reason": "guard_false"}
            )
        case RetryWatched(baseline=baseline):
            return Watch(baseline)
        case RetryFailed(rerun=rerun):
            return _retry_failed(job, rerun, now)
        case AwaitingApproval():
            return Await(StepStatus.AWAITING_APPROVAL, None)
        case AwaitingAnswer(question=question):
            return Await(StepStatus.AWAITING_ANSWER, question)
        case AwaitingManual():
            return Await(StepStatus.AWAITING_MANUAL, None)
        case GuardPending():
            return Hold()
        case WaitScheduled(seconds=seconds):
            return Delay(now + timedelta(seconds=seconds), f"Waiting {seconds} s")
        case _:
            assert_never(outcome)


def _failed(outcome: StepFailed | StepTimedOut, failures_added: int) -> Finish:
    match outcome:
        case StepFailed(error=error):
            return Finish(
                StepStatus.FAILED, error, AuditAction.STEP_FAILED, attempted=True, failures_added=failures_added
            )
        case StepTimedOut(seconds=seconds):
            return Finish(
                StepStatus.FAILED,
                f"Timed out after {seconds:g} s",
                AuditAction.STEP_FAILED,
                attempted=True,
                failures_added=failures_added,
                details={"reason": "timed_out"},
            )
        case _:
            assert_never(outcome)


def _retry_failed(job: StepJob, rerun: ActionResult, now: datetime) -> Finish:
    match rerun:
        case StepSucceeded(result=result):
            return Finish(
                StepStatus.SUCCEEDED,
                result,
                AuditAction.STEP_RETRY_FAILED,
                attempted=True,
                failures_added=1,
                baseline=job.occurrences,
                watch_at=now + WATCH_INTERVAL,
                details={"failures": job.failures(job.index) + 1},
            )
        case StepFailed() | StepTimedOut():
            # Both the watched attempt and the re-run failed.
            return _failed(rerun, failures_added=2)
        case _:
            assert_never(rerun)


def executed_action(job: StepJob, outcome: ResolvedOutcome) -> bool:
    """Whether `outcome` comes from an action that ran through an integration (`perform.run_action`)."""
    match outcome:
        case StepSucceeded() | StepFailed() | StepTimedOut() | RetryFailed():
            # A `wait` finishing and an escalation also succeed, but only `claims.start_step` sets an attempt key.
            return job.status is StepStatus.RUNNING and job.attempt_key is not None
        case (
            GaveUp()
            | GuardSkipped()
            | RetryWatched()
            | AwaitingApproval()
            | AwaitingAnswer()
            | AwaitingManual()
            | GuardPending()
            | WaitScheduled()
        ):
            return False
        case _:
            assert_never(outcome)
