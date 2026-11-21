"""Gates that hold a runbook step back before its action runs (SPEC §11.3, ADR-0088).

A step has two gates, checked in order: guard (`if`) and approval. Each gate reads what people have cleared on the step
and the run's state, and returns the outcome that holds the step, or None when it is open. A `manual` step then waits
to be ticked off (`plan.plan_step`); the decision endpoint marks it `succeeded`, so the executor never runs it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, assert_never

from pagercutie.pipeline.executor.outcomes import AwaitingAnswer, AwaitingApproval, GuardPending, GuardSkipped
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

type Held = GuardPending | GuardSkipped | AwaitingAnswer | AwaitingApproval
"""What a closed gate yields."""


@dataclass(frozen=True)
class Clearance:
    """Gates a person has already cleared on one step (ADR-0088), so the step is not stopped at them again."""

    guard_answered: bool = False
    approved: bool = False


class RunState(Protocol):
    """What gates may read from the runbook run."""

    def failures(self, index: int) -> int:
        """How many times step `index` has failed in this run."""
        ...

    def can_still_fail(self, index: int) -> bool:
        """Whether step `index` may still count a failure: it is unfinished, or a succeeded retry that is watched."""
        ...


class Gate(ABC):
    """One check before a step runs."""

    @abstractmethod
    def check(self, cleared: Clearance, run: RunState) -> Held | None:
        """The outcome that holds the step, or None when this gate is open."""


@dataclass(frozen=True)
class OpenGate(Gate):
    """Never holds the step back."""

    def check(self, cleared: Clearance, run: RunState) -> Held | None:
        return None


@dataclass(frozen=True)
class FailuresGuard(Gate):
    """Open once the guarded step has failed `failures_gte` times (SPEC §11.4). Below that, the step waits while the
    guarded step can still fail and is skipped once it cannot (ADR-0104)."""

    guard: StepGuard

    def check(self, cleared: Clearance, run: RunState) -> Held | None:
        failures = run.failures(self.guard.step)
        if failures >= self.guard.failures_gte:
            return None
        if run.can_still_fail(self.guard.step):
            return GuardPending()
        return GuardSkipped(
            f"Guard not met: step {self.guard.step + 1} failed {failures} of the {self.guard.failures_gte} times needed"
        )


@dataclass(frozen=True)
class QuestionGuard(Gate):
    """An unparsed guard: waits until a person answers `question` with yes (SPEC §11.4)."""

    question: str

    def check(self, cleared: Clearance, run: RunState) -> Held | None:
        return None if cleared.guard_answered else AwaitingAnswer(self.question)


@dataclass(frozen=True)
class ApprovalGate(Gate):
    """Waits until a user with the right role approves the step (RUN-4)."""

    def check(self, cleared: Clearance, run: RunState) -> Held | None:
        return None if cleared.approved else AwaitingApproval()


@dataclass(frozen=True)
class StepGates:
    """The gates of one step, checked before it runs. Built by `step_gates`."""

    guard: Gate
    approval: Gate

    def check(self, cleared: Clearance, run: RunState) -> Held | None:
        """The first closed gate's outcome in the order guard, approval; None when the step may run."""
        held = self.guard.check(cleared, run)
        return held if held is not None else self.approval.check(cleared, run)


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
    """Build the gates of `step` from its `if` guard and its approval default (SPEC §11.2)."""
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
    return StepGates(guard=guard, approval=approval)
