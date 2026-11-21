"""What running a step yields; `complete_step` maps each outcome to the step run's row (SPEC §11.3)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StepSucceeded:
    # Shown on the alert, e.g. "HTTP 200 in 35 ms".
    result: str


@dataclass(frozen=True)
class StepFailed:
    error: str


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
    """The step's structured guard is still false, so the step stays `pending` until the guarded step's failures
    reach the threshold (SPEC §11.4)."""


@dataclass(frozen=True)
class WaitScheduled:
    """A `wait` step started; the loop claims it again after `seconds`."""

    seconds: int


@dataclass(frozen=True)
class StepSkipped:
    """A lead rejected the step or a human answered its guard question with no (DOMAIN §6)."""


type StepOutcome = (
    StepSucceeded
    | StepFailed
    | AwaitingApproval
    | AwaitingAnswer
    | AwaitingManual
    | GuardPending
    | WaitScheduled
    | StepSkipped
)
