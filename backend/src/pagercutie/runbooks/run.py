"""A runbook run: the state machine that performs one runbook's actions for one alert (SPEC §11.3, DOMAIN §6).

Pure and in-memory: the service loads it from and saves it to Postgres. It owns the run's context (every step's
state); each action's result is applied back to that context. Each step's gates (`gates.StepGates`) read that
context and what humans have cleared to decide whether the step may run.
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import assert_never

from pydantic import JsonValue

from pagercutie.alerts.schemas import StepDecisionKind, StepStatus
from pagercutie.core.errors import Conflict, FieldError, InvalidInput
from pagercutie.runbooks.actions import ActionContext, ActionResult
from pagercutie.runbooks.factory import GateFactory
from pagercutie.runbooks.gates import Clearance, StepGates
from pagercutie.runbooks.steps import Step, StepGuard

_FINISHED = frozenset({StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED})


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class StepRun:
    index: int
    step: Step
    gates: StepGates
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    failures: int = 0
    result: str | None = None
    outputs: Mapping[str, JsonValue] = field(default_factory=dict)
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    cleared: Clearance = field(default_factory=Clearance)


@dataclass(frozen=True)
class StepTransition:
    """One audit entry (RUN-5): `by` is the deciding user, or None when the run moved on by itself."""

    index: int
    status: StepStatus
    at: datetime
    by: uuid.UUID | None = None
    decision: StepDecisionKind | None = None


class RunbookRun:
    def __init__(
        self,
        alert_id: uuid.UUID,
        runbook_id: uuid.UUID,
        steps: Sequence[Step],
        gates: GateFactory,
        context: ActionContext,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        _check_guards(steps)
        self.alert_id = alert_id
        self.runbook_id = runbook_id
        self.steps = [
            StepRun(index=index, step=step, gates=step_gates)
            for index, (step, step_gates) in enumerate(zip(steps, gates.create_all(steps), strict=True))
        ]
        self.transitions: list[StepTransition] = []
        self._context = context
        self._now = now

    @property
    def is_finished(self) -> bool:
        return all(s.status in _FINISHED for s in self.steps)

    def failures(self, index: int) -> int:
        """How many times step `index` has failed in this run (`gates.RunState`)."""
        return self.steps[index].failures

    async def advance(self) -> None:
        """Run steps in order until one has to wait: for a human, or for its guard to become true."""
        for step_run in self.steps:
            if step_run.status in _FINISHED:
                continue
            waiting_for = step_run.gates.waiting_for(step_run.cleared, self)
            if waiting_for is not None:
                self._move(step_run, waiting_for)
                return
            await self._execute(step_run)

    async def decide(self, index: int, decision: StepDecisionKind, user_id: uuid.UUID) -> None:
        """Apply a human decision (DOMAIN §6), then continue the run. `Conflict` if the step is not waiting for it."""
        step_run = self.steps[index]
        expected = _EXPECTED_STATUS[decision]
        if step_run.status is not expected:
            raise Conflict(f"Step {index} is {step_run.status}, '{decision}' needs {expected}")
        at = self._now()
        step_run.decided_by, step_run.decided_at = user_id, at
        self.transitions.append(StepTransition(index, step_run.status, at, by=user_id, decision=decision))
        match decision:
            case StepDecisionKind.APPROVE:
                step_run.cleared.approved = True
            case StepDecisionKind.YES:
                step_run.cleared.guard_answered = True
            case StepDecisionKind.DONE:
                step_run.cleared.done = True
            case StepDecisionKind.REJECT | StepDecisionKind.NO:
                self._move(step_run, StepStatus.SKIPPED, by=user_id)
            case _:
                assert_never(decision)
        await self.advance()

    async def _execute(self, step_run: StepRun) -> None:
        action = step_run.step.run(self._context)
        if action is None:
            # A step with nothing to run (`manual`) succeeds once its gates are open.
            self._move(step_run, StepStatus.SUCCEEDED)
            return
        self._move(step_run, StepStatus.RUNNING)
        step_run.attempts += 1
        self._apply(step_run, await action.run())

    def _apply(self, step_run: StepRun, result: ActionResult) -> None:
        """Fold an action's result back into the run's context. A failed step does not stop the run: later steps
        may be guarded on its failures (e.g. escalate once a retry failed twice)."""
        step_run.result = result.summary
        step_run.outputs = result.outputs
        if not result.ok:
            step_run.failures += 1
        self._move(step_run, StepStatus.SUCCEEDED if result.ok else StepStatus.FAILED)

    def _move(self, step_run: StepRun, status: StepStatus, by: uuid.UUID | None = None) -> None:
        if step_run.status is status:
            return
        step_run.status = status
        self.transitions.append(StepTransition(step_run.index, status, self._now(), by=by))


_EXPECTED_STATUS: dict[StepDecisionKind, StepStatus] = {
    StepDecisionKind.APPROVE: StepStatus.AWAITING_APPROVAL,
    StepDecisionKind.REJECT: StepStatus.AWAITING_APPROVAL,
    StepDecisionKind.YES: StepStatus.AWAITING_ANSWER,
    StepDecisionKind.NO: StepStatus.AWAITING_ANSWER,
    StepDecisionKind.DONE: StepStatus.AWAITING_MANUAL,
}


def _check_guards(steps: Sequence[Step]) -> None:
    errors = [
        FieldError(("steps", index, "if", "step"), "must reference an earlier step")
        for index, step in enumerate(steps)
        if isinstance(step.if_, StepGuard) and step.if_.step >= index
    ]
    if errors:
        raise InvalidInput(errors)
