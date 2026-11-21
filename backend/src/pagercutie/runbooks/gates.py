"""Gates that hold a runbook step back before its action runs (SPEC §11.3, ADR-0038).

A step has three gates, checked in order: guard (`if`), approval, manual confirmation. Each gate reads what humans
have cleared on the step and the run's state, and returns the status the step must wait in, or None when it is open.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

from pagercutie.alerts.schemas import StepStatus
from pagercutie.runbooks.actions import Action
from pagercutie.runbooks.steps import StepGuard


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
class StepHandler:
    """Everything needed to run one step: its gates and its action. Built by `factory.StepFactory`."""

    guard: Gate
    approval: Gate
    confirmation: Gate
    action: Action

    def waiting_for(self, cleared: Clearance, run: RunState) -> StepStatus | None:
        """The first closed gate's status in the order guard, approval, confirmation; None when the action may run."""
        for gate in (self.guard, self.approval, self.confirmation):
            status = gate.waiting_for(cleared, run)
            if status is not None:
                return status
        return None
