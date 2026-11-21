"""Gates that hold a runbook step back before its action runs (SPEC §11.3, ADR-0087).

A step has three gates, checked in order: guard (`if`), approval, manual confirmation. Each gate reads what humans
have cleared on the step and the run's state, and returns the status the step must wait in, or None when it is open.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Protocol, assert_never

from pagercutie.alerts.schemas import StepStatus
from pagercutie.runbooks.steps import (
    CallWebhook,
    Escalate,
    HttpGet,
    Manual,
    OpenTicket,
    RestartService,
    RetryWorkflow,
    Step,
    StepGuard,
    Wait,
)

type WaitingStatus = Literal[
    StepStatus.PENDING, StepStatus.AWAITING_APPROVAL, StepStatus.AWAITING_ANSWER, StepStatus.AWAITING_MANUAL
]
"""The statuses a closed gate can hold a step in."""


@dataclass
class Clearance:
    """Gates a human has already cleared on one step, so the step is not stopped at them again."""

    guard_answered: bool = False
    approved: bool = False
    done: bool = False


class RunState(Protocol):
    """What gates may read from the runbook run."""

    def failures(self, index: int) -> int:
        """How many times step `index` has failed in this run."""
        ...


class Gate(ABC):
    """One check before a step runs."""

    @abstractmethod
    def waiting_for(self, cleared: Clearance, run: RunState) -> WaitingStatus | None:
        """The status the step must wait in, or None when this gate is open."""


@dataclass(frozen=True)
class OpenGate(Gate):
    """Never holds the step back."""

    def waiting_for(self, cleared: Clearance, run: RunState) -> WaitingStatus | None:
        return None


@dataclass(frozen=True)
class FailuresGuard(Gate):
    """Keeps the step `pending` until the guarded step has failed `failures_gte` times (SPEC §11.4)."""

    guard: StepGuard

    def waiting_for(self, cleared: Clearance, run: RunState) -> WaitingStatus | None:
        return StepStatus.PENDING if run.failures(self.guard.step) < self.guard.failures_gte else None


@dataclass(frozen=True)
class QuestionGuard(Gate):
    """An unparsed guard: waits until a human answers `question` with yes (SPEC §11.4)."""

    question: str

    def waiting_for(self, cleared: Clearance, run: RunState) -> WaitingStatus | None:
        return None if cleared.guard_answered else StepStatus.AWAITING_ANSWER


@dataclass(frozen=True)
class ApprovalGate(Gate):
    """Waits until a user with the right role approves the step (RUN-4)."""

    def waiting_for(self, cleared: Clearance, run: RunState) -> WaitingStatus | None:
        return None if cleared.approved else StepStatus.AWAITING_APPROVAL


@dataclass(frozen=True)
class ManualGate(Gate):
    """Waits until a human ticks off a `manual` step."""

    def waiting_for(self, cleared: Clearance, run: RunState) -> WaitingStatus | None:
        return None if cleared.done else StepStatus.AWAITING_MANUAL


@dataclass(frozen=True)
class StepGates:
    """The gates of one step, checked before it runs. Built by `step_gates`."""

    guard: Gate
    approval: Gate
    confirmation: Gate

    def waiting_for(self, cleared: Clearance, run: RunState) -> WaitingStatus | None:
        """The first closed gate's status in the order guard, approval, confirmation; None when the step may run."""
        for gate in (self.guard, self.approval, self.confirmation):
            status = gate.waiting_for(cleared, run)
            if status is not None:
                return status
        return None


def requires_approval(step: Step) -> bool:
    """Risk defaults (RUN-4): read-only actions need no approval, risky ones do; a step may only make it stricter."""
    if step.approval == "required":
        return True
    match step:
        # `retry_workflow` is `none`: the brief's runbook sets `approval: none` on it, which may never loosen a default.
        case HttpGet() | RetryWorkflow() | OpenTicket() | Wait() | Manual():
            return False
        case RestartService() | CallWebhook() | Escalate():
            return True
        case _:
            assert_never(step)


def step_gates(step: Step) -> StepGates:
    """Build the gates of `step` from its `if` guard, its approval default and its type (SPEC §11.2)."""
    guard: Gate
    match step.if_:
        case None:
            guard = OpenGate()
        case StepGuard():
            guard = FailuresGuard(step.if_)
        case str():
            guard = QuestionGuard(step.if_)
        case _:
            assert_never(step.if_)
    approval: Gate = ApprovalGate() if requires_approval(step) else OpenGate()
    confirmation: Gate = ManualGate() if isinstance(step, Manual) else OpenGate()
    return StepGates(guard=guard, approval=approval, confirmation=confirmation)


def clearance(status: StepStatus, guard_answered: bool, approved: bool) -> Clearance:
    """Gates already cleared on a step: the flags the decision endpoint stored (ADR-0087).

    A `running` step (a `wait` in its delay) has passed every gate. `done` is never set here: the endpoint marks a
    manual step succeeded, so the executor only sees an unticked manual step and `ManualGate` holds it.
    """
    if status is StepStatus.RUNNING:
        return Clearance(guard_answered=True, approved=True)
    return Clearance(guard_answered=guard_answered, approved=approved)
