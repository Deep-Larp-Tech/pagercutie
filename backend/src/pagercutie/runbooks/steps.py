"""Runbook steps (SPEC §11.2). A discriminated union on `action`, the key the brief's YAML uses.

A step and its action live together (ADR-0039): every step implements `run()`, which returns the step's action, or
None when there is nothing to run (`manual`). Adding an action: add the model to `Step` with its `run()` and a
default approval, regenerate the contract, then handle it everywhere the type checkers point at (SPEC §4.4).
"""

from abc import abstractmethod
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from pagercutie.core.schemas import InputModel, LongText, ShortText, Slug, Template
from pagercutie.runbooks.actions import Action, ActionContext

type Step = Annotated[
    HttpGet | RetryWorkflow | RestartService | CallWebhook | OpenTicket | Escalate | Wait | Manual,
    Field(discriminator="action"),
]


class StepGuard(InputModel):
    """Run the step only once step `step` (index) has failed at least `failures_gte` times."""

    step: int = Field(ge=0)
    failures_gte: int = Field(ge=1)


class StepBase(InputModel):
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True, serialize_by_alias=True)

    check: ShortText | None = Field(default=None, description="Question shown to humans, e.g. 'Is X healthy?'")
    if_: StepGuard | LongText | None = Field(
        default=None,
        alias="if",
        description="Structured guard, or free text that a human answers yes/no when it cannot be parsed",
    )
    approval: Literal["none", "required"] | None = Field(
        default=None, description="null: the action's default; a runbook may only make it stricter"
    )

    @abstractmethod
    def run(self, context: ActionContext) -> Action | None:
        """The action that performs this step, or None when the step has nothing to run."""


class HttpGet(StepBase):
    action: Literal["http_get"]
    url: Template

    def run(self, context: ActionContext) -> Action:
        raise NotImplementedError("http_get")


class RetryWorkflow(StepBase):
    action: Literal["retry_workflow"]
    workflow_id: Template = Field(alias="workflowId")

    def run(self, context: ActionContext) -> Action:
        raise NotImplementedError("retry_workflow")


class RestartService(StepBase):
    action: Literal["restart_service"]
    service: Template

    def run(self, context: ActionContext) -> Action:
        raise NotImplementedError("restart_service")


class CallWebhook(StepBase):
    action: Literal["call_webhook"]
    url: Template
    method: Literal["GET", "POST", "PUT"] = "POST"

    def run(self, context: ActionContext) -> Action:
        raise NotImplementedError("call_webhook")


class OpenTicket(StepBase):
    action: Literal["open_ticket"]
    title: Template

    def run(self, context: ActionContext) -> Action:
        raise NotImplementedError("open_ticket")


class Escalate(StepBase):
    """`team` is a slug, not an ID: runbooks are written by people (the brief's YAML: `team: counterparty-support`)."""

    action: Literal["escalate"]
    team: Slug

    def run(self, context: ActionContext) -> Action:
        raise NotImplementedError("escalate")


class Wait(StepBase):
    action: Literal["wait"]
    seconds: int = Field(ge=1, le=86_400)

    def run(self, context: ActionContext) -> Action:
        raise NotImplementedError("wait")


class Manual(StepBase):
    """A human instruction, ticked off as done. Markdown and free-text runbooks become these."""

    action: Literal["manual"]
    text: Template

    def run(self, context: ActionContext) -> None:
        """None: the step is done when a human ticks it off."""
        return None
