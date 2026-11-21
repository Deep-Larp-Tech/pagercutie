from collections.abc import Mapping

import pytest
from pydantic import JsonValue, TypeAdapter

from pagercutie.pipeline.executor.gates import (
    ApprovalGate,
    Clearance,
    FailuresGuard,
    OpenGate,
    QuestionGuard,
    StepGates,
    requires_approval,
    step_gates,
)
from pagercutie.pipeline.executor.outcomes import AwaitingAnswer, AwaitingApproval, GuardPending, GuardSkipped
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
    def __init__(self, failures: Mapping[int, int], unsettled: frozenset[int] = frozenset()) -> None:
        self._failures = failures
        self._unsettled = unsettled

    def failures(self, index: int) -> int:
        return self._failures.get(index, 0)

    def can_still_fail(self, index: int) -> bool:
        return index in self._unsettled


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


def test_approval_gates() -> None:
    assert step_gates(make_step("http_get")) == StepGates(OpenGate(), OpenGate())
    assert step_gates(make_step("escalate")).approval == ApprovalGate()
    assert step_gates(make_step("manual", approval="required")) == StepGates(OpenGate(), ApprovalGate())


def test_gates_close_in_order_guard_then_approval() -> None:
    gates = StepGates(QuestionGuard("q"), ApprovalGate())
    run = FakeRun({})
    assert gates.check(Clearance(), run) == AwaitingAnswer("q")
    assert gates.check(Clearance(guard_answered=True), run) == AwaitingApproval()
    assert gates.check(Clearance(guard_answered=True, approved=True), run) is None


def test_failures_guard_opens_at_threshold() -> None:
    guard = FailuresGuard(StepGuard(step=1, failures_gte=2))
    assert guard.check(Clearance(), FakeRun({1: 2})) is None
    assert guard.check(Clearance(), FakeRun({1: 3})) is None


def test_failures_guard_below_threshold_waits_only_while_the_guarded_step_can_fail() -> None:
    guard = FailuresGuard(StepGuard(step=1, failures_gte=2))
    assert guard.check(Clearance(), FakeRun({1: 1}, unsettled=frozenset({1}))) == GuardPending()
    assert guard.check(Clearance(), FakeRun({1: 1})) == GuardSkipped(
        "Guard not met: step 2 failed 1 of the 2 times needed"
    )
    assert guard.check(Clearance(), FakeRun({0: 5})) == GuardSkipped(
        "Guard not met: step 2 failed 0 of the 2 times needed"
    )
