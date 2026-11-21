"""Gates that hold a runbook step back before its action runs (SPEC §11.3, ADR-0073).

A step has three gates, checked in order: guard (`if`), approval, manual confirmation. Each gate reads what humans
have cleared on the step and the run's state, and returns the status the step must wait in, or None when it is open.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Protocol, assert_never

from pagercutie.alerts.schemas import StepDecisionKind, StepStatus
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
    def waiting_for(self, cleared: Clearance, run: RunState) -> StepStatus | None:
        """The status the step must wait in, or None when this gate is open."""


@dataclass(frozen=True)
class OpenGate(Gate):
    """Never holds the step back."""

    def waiting_for(self, cleared: Clearance, run: RunState) -> StepStatus | None:
        return None


@dataclass(frozen=True)
class FailuresGuard(Gate):
    """Keeps the step `pending` until the guarded step has failed `failures_gte` times (SPEC §11.4)."""

    guard: StepGuard

    def waiting_for(self, cleared: Clearance, run: RunState) -> StepStatus | None:
        return StepStatus.PENDING if run.failures(self.guard.step) < self.guard.failures_gte else None


@dataclass(frozen=True)
class QuestionGuard(Gate):
    """An unparsed guard: waits until a human answers `question` with yes (SPEC §11.4)."""

    question: str

    def waiting_for(self, cleared: Clearance, run: RunState) -> StepStatus | None:
        return None if cleared.guard_answered else StepStatus.AWAITING_ANSWER


@dataclass(frozen=True)
class ApprovalGate(Gate):
    """Waits until a user with the right role approves the step (RUN-4)."""

    def waiting_for(self, cleared: Clearance, run: RunState) -> StepStatus | None:
        return None if cleared.approved else StepStatus.AWAITING_APPROVAL


@dataclass(frozen=True)
class ManualGate(Gate):
    """Waits until a human ticks off a `manual` step."""

    def waiting_for(self, cleared: Clearance, run: RunState) -> StepStatus | None:
        return None if cleared.done else StepStatus.AWAITING_MANUAL


@dataclass(frozen=True)
class StepGates:
    """The gates of one step, checked before it runs. Built by `step_gates`."""

    guard: Gate
    approval: Gate
    confirmation: Gate

    def waiting_for(self, cleared: Clearance, run: RunState) -> StepStatus | None:
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


def expected_status(decision: StepDecisionKind) -> StepStatus:
    """The status a step must be in for `decision` to apply (DOMAIN §6)."""
    match decision:
        case StepDecisionKind.APPROVE | StepDecisionKind.REJECT:
            return StepStatus.AWAITING_APPROVAL
        case StepDecisionKind.YES | StepDecisionKind.NO:
            return StepStatus.AWAITING_ANSWER
        case StepDecisionKind.DONE:
            return StepStatus.AWAITING_MANUAL
        case _:
            assert_never(decision)


def clearance(status: StepStatus, decision: StepDecisionKind | None) -> Clearance:
    """Gates already cleared on a step, from where it waits and its latest decision (ADR-0073).

    Gates are passed in order, so a step waiting at a later gate has passed the earlier ones. `reject` and `no`
    clear nothing: the executor skips the step.
    """
    match status:
        case StepStatus.AWAITING_APPROVAL:
            cleared = Clearance(guard_answered=True)
        case StepStatus.AWAITING_MANUAL:
            cleared = Clearance(guard_answered=True, approved=True)
        case (
            StepStatus.PENDING
            | StepStatus.AWAITING_ANSWER
            | StepStatus.RUNNING
            | StepStatus.SUCCEEDED
            | StepStatus.FAILED
            | StepStatus.SKIPPED
        ):
            cleared = Clearance()
        case _:
            assert_never(status)
    if decision is None or expected_status(decision) is not status:
        return cleared
    match decision:
        case StepDecisionKind.YES:
            return replace(cleared, guard_answered=True)
        case StepDecisionKind.APPROVE:
            return replace(cleared, approved=True)
        case StepDecisionKind.DONE:
            return replace(cleared, done=True)
        case StepDecisionKind.REJECT | StepDecisionKind.NO:
            return cleared
        case _:
            assert_never(decision)
