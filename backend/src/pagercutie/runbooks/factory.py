"""Turns parsed runbook steps into actions.

Every runbook format (structured, Markdown, text, link) is parsed into the same `Step` union first (SPEC §11.1).
A concrete factory implements one method per step type. A new step type makes `ty check` fail on the exhaustive
`match` until it gets its method here (SPEC §4.4).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import assert_never

from pagercutie.runbooks.actions import Action
from pagercutie.runbooks.steps import (
    CallWebhook,
    Escalate,
    HttpGet,
    Manual,
    OpenTicket,
    RestartService,
    RetryWorkflow,
    Step,
    Wait,
)


class ActionFactory(ABC):
    def create(self, step: Step) -> Action:
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

    def create_all(self, steps: Sequence[Step]) -> list[Action]:
        return [self.create(step) for step in steps]

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
