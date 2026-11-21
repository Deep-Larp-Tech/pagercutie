from collections.abc import Mapping

import pytest
from pydantic import JsonValue, TypeAdapter

from pagercutie.alerts.schemas import StepStatus
from pagercutie.pipeline.executor.gates import (
    ApprovalGate,
    Clearance,
    FailuresGuard,
    ManualGate,
    OpenGate,
    QuestionGuard,
    StepGates,
    clearance,
    requires_approval,
    step_gates,
)
from pagercutie.runbooks.steps import Step, StepGuard

STEP = TypeAdapter(Step)

ACTIONS: dict[str, dict[str, JsonValue]] = {
    "http_get": {"url": "http://x/health"},
    "retry_workflow": {"workflowId": "wf-1"},
    "restart_service": {"service": "svc"},
    "call_webhook": {"url": "http://x/hook"},
    "open_ticket": {"title": "t"},
    "escalate": {"team": "support"},
    "wait": {"seconds": 5},
    "manual": {"text": "do it"},
}
RISKY = {"restart_service", "call_webhook", "escalate"}


def make_step(action: str, **extra: JsonValue) -> Step:
    return STEP.validate_python({"action": action, **ACTIONS[action], **extra})


class FakeRun:
    def __init__(self, failures: Mapping[int, int]) -> None:
        self._failures = failures

    def failures(self, index: int) -> int:
        return self._failures.get(index, 0)


@pytest.mark.parametrize("action", ACTIONS)
def test_default_approval_follows_risk(action: str) -> None:
    assert requires_approval(make_step(action)) is (action in RISKY)
    assert requires_approval(make_step(action, approval="none")) is (action in RISKY)


@pytest.mark.parametrize("action", ACTIONS)
def test_runbook_can_make_a_step_stricter(action: str) -> None:
    assert requires_approval(make_step(action, approval="required")) is True


def test_guard_kinds_map_to_gates() -> None:
    assert step_gates(make_step("wait")).guard == OpenGate()
    guard = StepGuard(step=0, failures_gte=2)
    assert step_gates(make_step("wait", **{"if": guard.model_dump()})).guard == FailuresGuard(guard)
    assert step_gates(make_step("wait", **{"if": "is it raining?"})).guard == QuestionGuard("is it raining?")


def test_approval_and_confirmation_gates() -> None:
    assert step_gates(make_step("http_get")) == StepGates(OpenGate(), OpenGate(), OpenGate())
    assert step_gates(make_step("escalate")).approval == ApprovalGate()
    assert step_gates(make_step("manual")).confirmation == ManualGate()
    assert step_gates(make_step("manual", approval="required")) == StepGates(OpenGate(), ApprovalGate(), ManualGate())


def test_gates_close_in_order_guard_approval_confirmation() -> None:
    gates = StepGates(QuestionGuard("q"), ApprovalGate(), ManualGate())
    run = FakeRun({})
    assert gates.waiting_for(Clearance(), run) is StepStatus.AWAITING_ANSWER
    assert gates.waiting_for(Clearance(guard_answered=True), run) is StepStatus.AWAITING_APPROVAL
    assert gates.waiting_for(Clearance(guard_answered=True, approved=True), run) is StepStatus.AWAITING_MANUAL
    assert gates.waiting_for(Clearance(guard_answered=True, approved=True, done=True), run) is None


def test_failures_guard_opens_at_threshold() -> None:
    guard = FailuresGuard(StepGuard(step=1, failures_gte=2))
    assert guard.waiting_for(Clearance(), FakeRun({1: 1})) is StepStatus.PENDING
    assert guard.waiting_for(Clearance(), FakeRun({1: 2})) is None
    assert guard.waiting_for(Clearance(), FakeRun({1: 3})) is None
    assert guard.waiting_for(Clearance(), FakeRun({0: 5})) is StepStatus.PENDING


@pytest.mark.parametrize(
    ("status", "guard_answered", "approved", "expected"),
    [
        (StepStatus.PENDING, False, False, Clearance()),
        (StepStatus.AWAITING_ANSWER, False, False, Clearance()),
        (StepStatus.PENDING, True, False, Clearance(guard_answered=True)),
        (StepStatus.PENDING, True, True, Clearance(guard_answered=True, approved=True)),
        (StepStatus.AWAITING_APPROVAL, False, True, Clearance(approved=True)),
        (StepStatus.AWAITING_MANUAL, True, True, Clearance(guard_answered=True, approved=True)),
        (StepStatus.RUNNING, False, False, Clearance(guard_answered=True, approved=True)),
    ],
)
def test_clearance_from_status_and_stored_flags(
    status: StepStatus, guard_answered: bool, approved: bool, expected: Clearance
) -> None:
    assert clearance(status, guard_answered, approved) == expected
