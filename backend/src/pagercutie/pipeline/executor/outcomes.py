"""What running a step yields; `transitions.transition` maps each outcome to the step run's next state (SPEC §11.3)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StepSucceeded:
    # Shown on the alert, e.g. "HTTP 200 in 35 ms".
    result: str


@dataclass(frozen=True)
class StepFailed:
    error: str


@dataclass(frozen=True)
class StepTimedOut:
    """The action did not answer within the step timeout, which is shorter than the lease (ADR-0109)."""

    seconds: float


type ActionResult = StepSucceeded | StepFailed | StepTimedOut
"""What an action attempt through an integration yields."""


@dataclass(frozen=True)
class AwaitingApproval:
    """The action needs a lead's approval before it runs (RUN-4)."""


@dataclass(frozen=True)
class AwaitingAnswer:
    """An unparsed `if` guard waits for a yes or no in the UI (SPEC §11.4)."""

    question: str


@dataclass(frozen=True)
class AwaitingManual:
    """A `manual` step waits to be ticked off."""


@dataclass(frozen=True)
class GuardPending:
    """The step's structured guard is not met yet and the guarded step can still fail (a succeeded retry is watched),
    so the step stays `pending` until that step counts a failure (SPEC §11.4)."""


@dataclass(frozen=True)
class GuardSkipped:
    """The step's structured guard is false for good: the guarded step is final and failed fewer times than the guard
    needs. The step is skipped and the run goes on (ADR-0107)."""

    reason: str


@dataclass(frozen=True)
class WaitScheduled:
    """A `wait` step started; the loop claims it again after `seconds`."""

    seconds: int


@dataclass(frozen=True)
class RetryWatched:
    """A succeeded `retry_workflow` saw no occurrence of the alert after it ran; it is checked again later (SPEC §11.4).

    `baseline` is the new `occurrences_at_run` when occurrences arrived that were seen no later than the attempt
    started (a late counter flush), so they never count as a failure; None keeps the baseline.
    """

    baseline: int | None = None


@dataclass(frozen=True)
class RetryFailed:
    """An occurrence arrived after the retry ran, so that attempt failed (ADR-0020, SPEC §11.4).

    `rerun` is the result of running the retry again.
    """

    rerun: ActionResult


@dataclass(frozen=True)
class EscalationDue:
    """An `escalate` step passed its gates; `complete_step` adds the team named by the slug `team` to the alert and
    creates its deliveries in the outcome's transaction (SPEC §11.4 step 5)."""

    team: str


@dataclass(frozen=True)
class GaveUp:
    """The step's claims ended without an outcome `errors` times, so it fails instead of being claimed again
    (ADR-0106)."""

    errors: int


type ResolvedOutcome = (
    StepSucceeded
    | StepFailed
    | StepTimedOut
    | AwaitingApproval
    | AwaitingAnswer
    | AwaitingManual
    | GuardPending
    | GuardSkipped
    | WaitScheduled
    | RetryWatched
    | RetryFailed
    | GaveUp
)
"""Outcomes `transitions.transition` maps directly; `complete_step` resolves `EscalationDue` to one of them."""

type StepOutcome = ResolvedOutcome | EscalationDue
"""Everything planning or running a step yields."""
