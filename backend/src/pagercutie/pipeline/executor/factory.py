"""Builds the gates of parsed runbook steps (SPEC §11.2, §11.3, ADR-0042, ADR-0043).

Every runbook format (structured, Markdown, text, link) is parsed into the same `Step` union first (SPEC §11.1).
`GateFactory.create` builds a step's gates from its `if` guard, its approval and its type. A concrete factory
implements one method per guard kind. Actions are not built here: each step returns its own (`Step.run`).

Approval and confirmation gates are final: they come from the risk defaults, which an implementation may not
loosen (RUN-4).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import assert_never, final

from pagercutie.pipeline.executor.gates import ApprovalGate, Gate, ManualGate, OpenGate, StepGates
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


class GateFactory(ABC):
    @final
    def create(self, step: Step) -> StepGates:
        return StepGates(guard=self.guard(step.if_), approval=self.approval(step), confirmation=self.confirmation(step))

    @final
    def create_all(self, steps: Sequence[Step]) -> list[StepGates]:
        return [self.create(step) for step in steps]

    @final
    def guard(self, if_: StepGuard | str | None) -> Gate:
        match if_:
            case None:
                return OpenGate()
            case StepGuard():
                return self.failures_guard(if_)
            case str():
                return self.question_guard(if_)
            case _:
                assert_never(if_)

    @final
    def approval(self, step: Step) -> Gate:
        return ApprovalGate() if requires_approval(step) else OpenGate()

    @final
    def confirmation(self, step: Step) -> Gate:
        return ManualGate() if isinstance(step, Manual) else OpenGate()

    @abstractmethod
    def failures_guard(self, guard: StepGuard) -> Gate:
        """Gate for a structured guard: run once step `guard.step` has failed `guard.failures_gte` times."""

    @abstractmethod
    def question_guard(self, question: str) -> Gate:
        """Gate for guard text no rule could parse: a human answers it yes / no (SPEC §11.4)."""


def requires_approval(step: Step) -> bool:
    """Risk defaults (RUN-4): read-only actions need no approval, risky ones do; a step may only make it stricter."""
    if step.approval == "required":
        return True
    match step:
        # `retry_workflow` is `none`: the brief's runbook sets `approval: none` on it, which may never loosen a default.
        case HttpGet() | RetryWorkflow() | OpenTicket() | Wait() | Manual():
            return False
        # `call_webhook` is `required`: unlike `http_get`, a webhook can do anything.
        case RestartService() | CallWebhook() | Escalate():
            return True
        case _:
            assert_never(step)
