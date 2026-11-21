"""Turns parsed runbook steps into step handlers: the step's gates plus its action (SPEC §11.2, ADR-0038).

Every runbook format (structured, Markdown, text, link) is parsed into the same `Step` union first (SPEC §11.1).
`StepFactory.create` matches the whole step: its `if` guard, its approval, whether it is `manual`, and its action.
A concrete factory implements one method per guard kind and per step type. A new step type or guard kind makes
`ty check` fail on the exhaustive `match` until it gets its method here (SPEC §4.4).

Approval and confirmation gates are final: they come from the risk defaults, which an implementation may not
loosen (RUN-4).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import assert_never, final

from pagercutie.runbooks.actions import Action
from pagercutie.runbooks.gates import ApprovalGate, Gate, ManualGate, OpenGate, StepHandler
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


class StepFactory(ABC):
    @final
    def create(self, step: Step) -> StepHandler:
        return StepHandler(
            guard=self.guard(step.if_),
            approval=self.approval(step),
            confirmation=self.confirmation(step),
            action=self.action(step),
        )

    @final
    def create_all(self, steps: Sequence[Step]) -> list[StepHandler]:
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

    @final
    def action(self, step: Step) -> Action:
        match step:
            case HttpGet():
                return self.http_get(step)
            case RetryWorkflow():
                return self.retry_workflow(step)
            case RestartService():
                return self.restart_service(step)
            case CallWebhook():
                return self.call_webhook(step)
            case OpenTicket():
                return self.open_ticket(step)
            case Escalate():
                return self.escalate(step)
            case Wait():
                return self.wait(step)
            case Manual():
                return self.manual(step)
            case _:
                assert_never(step)

    @abstractmethod
    def failures_guard(self, guard: StepGuard) -> Gate:
        """Gate for a structured guard: run once step `guard.step` has failed `guard.failures_gte` times."""

    @abstractmethod
    def question_guard(self, question: str) -> Gate:
        """Gate for guard text no rule could parse: a human answers it yes / no (SPEC §11.4)."""

    @abstractmethod
    def http_get(self, step: HttpGet) -> Action: ...

    @abstractmethod
    def retry_workflow(self, step: RetryWorkflow) -> Action: ...

    @abstractmethod
    def restart_service(self, step: RestartService) -> Action: ...

    @abstractmethod
    def call_webhook(self, step: CallWebhook) -> Action: ...

    @abstractmethod
    def open_ticket(self, step: OpenTicket) -> Action: ...

    @abstractmethod
    def escalate(self, step: Escalate) -> Action: ...

    @abstractmethod
    def wait(self, step: Wait) -> Action: ...

    @abstractmethod
    def manual(self, step: Manual) -> Action: ...


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
