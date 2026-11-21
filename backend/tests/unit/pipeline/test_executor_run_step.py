import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, assert_never

import httpx
import pytest
from pydantic import JsonValue, TypeAdapter

from pagercutie.alerts.schemas import StepStatus
from pagercutie.pipeline.executor.actions import (
    IDEMPOTENCY_HEADER,
    HttpError,
    HttpResult,
    HttpxClient,
    Integrations,
    SimulatedOps,
)
from pagercutie.pipeline.executor.outcomes import (
    AwaitingAnswer,
    AwaitingApproval,
    AwaitingManual,
    EscalationDue,
    GaveUp,
    GuardPending,
    GuardSkipped,
    RetryFailed,
    RetryWatched,
    StepFailed,
    StepOutcome,
    StepSucceeded,
    StepTimedOut,
    WaitScheduled,
)
from pagercutie.pipeline.executor.stage import Act, Settle, StepJob, plan_step, run_action
from pagercutie.rules.evaluator import EventView
from pagercutie.runbooks.steps import Step

pytestmark = pytest.mark.anyio

STEP = TypeAdapter(Step)
EVENT: EventView = {
    "source": "billing",
    "schema": "workflow_failed",
    "payload": {"workflowId": "wf-9"},
}
KEY = uuid.UUID("0193e4b0-0000-7000-8000-000000000001")
MAX_ERRORS = 5
TIMEOUT_S = 20.0
ACTED_AT = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@dataclass
class FakeHttp:
    result: HttpResult | HttpError = field(default_factory=lambda: HttpResult(status=200, elapsed_ms=35))
    calls: list[tuple[str, str, JsonValue | None]] = field(default_factory=list)
    keys: list[uuid.UUID] = field(default_factory=list)

    async def request(
        self, method: Literal["GET", "POST", "PUT"], url: str, json: JsonValue | None, idempotency_key: uuid.UUID
    ) -> HttpResult:
        self.calls.append((method, url, json))
        self.keys.append(idempotency_key)
        if isinstance(self.result, HttpError):
            raise self.result
        return self.result


def make_step(**step: JsonValue) -> Step:
    return STEP.validate_python(step)


def make_job(
    step: Step,
    status: StepStatus = StepStatus.PENDING,
    guard_answered: bool = False,
    approved: bool = False,
    attempts: int = 0,
    errors: int = 0,
    failures: dict[int, int] | None = None,
    unsettled: frozenset[int] = frozenset(),
    occurrences: int = 1,
    last_seen_at: datetime = ACTED_AT,
    occurrences_at_run: int | None = None,
    attempt_key: uuid.UUID | None = None,
    acted_at: datetime | None = None,
) -> StepJob:
    return StepJob(
        run_id=uuid.uuid4(),
        index=1,
        alert_id=uuid.uuid4(),
        team_id=None,
        step=step,
        status=status,
        guard_answered=guard_answered,
        approved=approved,
        decided_by=None,
        attempts=attempts,
        errors=errors,
        failures_by_index=failures or {},
        unsettled=unsettled,
        occurrences=occurrences,
        last_seen_at=last_seen_at,
        occurrences_at_run=occurrences_at_run,
        attempt_key=attempt_key,
        acted_at=acted_at,
        event=EVENT,
        due_at=datetime(2026, 11, 21, tzinfo=UTC),
        lease=datetime(2026, 11, 21, tzinfo=UTC),
        traceparent=None,
    )


async def run(job: StepJob, http: FakeHttp | None = None, ops: SimulatedOps | None = None) -> StepOutcome:
    """Plans the step and, when it acts, runs the action with `KEY`, as the loop does after `start_step`."""
    plan = plan_step(job, MAX_ERRORS)
    match plan:
        case Settle():
            return plan.outcome
        case Act():
            integrations = Integrations(http=http or FakeHttp(), ops=ops or SimulatedOps())
            return await run_action(job, plan, KEY, integrations, TIMEOUT_S)
        case _:
            assert_never(plan)


async def test_http_get_renders_the_url_and_reports_status_and_time() -> None:
    http = FakeHttp()

    outcome = await run(make_job(make_step(action="http_get", url="http://x/{{workflowId}}/{{schema}}")), http)

    assert outcome == StepSucceeded("HTTP 200 in 35 ms")
    assert http.calls == [("GET", "http://x/wf-9/workflow_failed", None)]
    assert http.keys == [KEY]


async def test_http_get_fails_on_a_non_2xx_status() -> None:
    http = FakeHttp(HttpResult(status=500, elapsed_ms=12))

    outcome = await run(make_job(make_step(action="http_get", url="http://x")), http)

    assert outcome == StepFailed("HTTP 500 in 12 ms")


async def test_http_get_fails_on_a_transport_error() -> None:
    http = FakeHttp(HttpError("timed out"))

    outcome = await run(make_job(make_step(action="http_get", url="http://x")), http)

    assert outcome == StepFailed("Request failed: timed out")


async def test_call_webhook_post_sends_the_event_view_after_approval() -> None:
    http = FakeHttp()
    step = make_step(action="call_webhook", url="http://x/{{payload.workflowId}}")
    job = make_job(step, StepStatus.PENDING, approved=True)

    outcome = await run(job, http)

    assert outcome == StepSucceeded("HTTP 200 in 35 ms")
    assert http.calls == [("POST", "http://x/wf-9", dict(EVENT))]


async def test_call_webhook_get_sends_no_body() -> None:
    http = FakeHttp()
    step = make_step(action="call_webhook", url="http://x", method="GET")

    await run(make_job(step, StepStatus.PENDING, approved=True), http)

    assert http.calls == [("GET", "http://x", None)]


async def test_call_webhook_put_sends_the_event_view() -> None:
    http = FakeHttp()
    step = make_step(action="call_webhook", url="http://x", method="PUT")

    await run(make_job(step, StepStatus.PENDING, approved=True), http)

    assert http.calls == [("PUT", "http://x", dict(EVENT))]


async def test_retry_workflow_renders_the_workflow_id() -> None:
    outcome = await run(make_job(make_step(action="retry_workflow", workflowId="{{workflowId}}")))

    assert outcome == StepSucceeded("Simulated: retry of workflow wf-9 accepted")


async def test_restart_service_renders_the_service_after_approval() -> None:
    step = make_step(action="restart_service", service="{{source}}-api")
    job = make_job(step, StepStatus.PENDING, approved=True)

    assert await run(job) == StepSucceeded("Simulated: restart of service billing-api accepted")


async def test_open_ticket_renders_the_title() -> None:
    outcome = await run(make_job(make_step(action="open_ticket", title="Failed {{payload.workflowId}}")))

    assert outcome == StepSucceeded("Simulated: ticket 'Failed wf-9' opened")


async def test_wait_is_scheduled_first_and_succeeds_once_running() -> None:
    step = make_step(action="wait", seconds=30)

    assert await run(make_job(step)) == WaitScheduled(30)
    assert await run(make_job(step, StepStatus.RUNNING, attempts=1)) == StepSucceeded("Waited 30 s")


async def test_an_approved_escalation_is_due_with_its_team() -> None:
    step = make_step(action="escalate", team="support")

    assert await run(make_job(step, StepStatus.PENDING, approved=True)) == EscalationDue("support")


async def test_a_step_that_needs_approval_waits_for_it() -> None:
    step = make_step(action="restart_service", service="s")

    assert await run(make_job(step)) == AwaitingApproval()


async def test_a_question_guard_asks_its_text() -> None:
    step = make_step(action="open_ticket", title="t", **{"if": "retry fails twice"})

    assert await run(make_job(step)) == AwaitingAnswer(question="retry fails twice")


async def test_a_cleared_question_guard_continues_to_the_action() -> None:
    step = make_step(action="open_ticket", title="t", **{"if": "is it bad?"})
    job = make_job(step, guard_answered=True)

    assert await run(job) == StepSucceeded("Simulated: ticket 't' opened")


async def test_a_cleared_question_guard_continues_to_the_approval_gate() -> None:
    step = make_step(action="restart_service", service="s", **{"if": "is it bad?"})
    job = make_job(step, guard_answered=True)

    assert await run(job) == AwaitingApproval()


GUARD: JsonValue = {"step": 0, "failures_gte": 2}


@pytest.mark.parametrize(
    ("failures", "unsettled", "expected"),
    [
        (1, frozenset({0}), GuardPending()),
        (1, frozenset(), GuardSkipped("Guard not met: step 1 failed 1 of the 2 times needed")),
        (2, frozenset(), StepSucceeded("Simulated: ticket 't' opened")),
        (2, frozenset({0}), StepSucceeded("Simulated: ticket 't' opened")),
    ],
    ids=["unknown", "false", "true", "true-while-watched"],
)
async def test_a_failures_guard_waits_while_the_guarded_step_can_fail_and_skips_once_it_cannot(
    failures: int, unsettled: frozenset[int], expected: StepOutcome
) -> None:
    step = make_step(action="open_ticket", title="t", **{"if": GUARD})

    assert await run(make_job(step, failures={0: failures}, unsettled=unsettled)) == expected


async def test_a_manual_step_waits_for_a_person_to_mark_it_done() -> None:
    step = make_step(action="manual", text="check the logs")

    assert await run(make_job(step)) == AwaitingManual()


async def test_a_manual_step_checks_its_approval_first() -> None:
    step = make_step(action="manual", text="check the logs", approval="required")

    assert await run(make_job(step)) == AwaitingApproval()
    assert await run(make_job(step, approved=True)) == AwaitingManual()


async def test_a_step_gives_up_at_the_error_bound_without_acting() -> None:
    http = FakeHttp()
    step = make_step(action="http_get", url="http://x")

    assert await run(make_job(step, errors=MAX_ERRORS), http) == GaveUp(MAX_ERRORS)
    assert http.calls == []
    assert await run(make_job(step, errors=MAX_ERRORS - 1), http) == StepSucceeded("HTTP 200 in 35 ms")


async def test_a_running_action_resumes_without_checking_the_gates_again() -> None:
    step = make_step(action="restart_service", service="s")
    job = make_job(step, StepStatus.RUNNING, attempt_key=KEY, acted_at=ACTED_AT)

    plan = plan_step(job, MAX_ERRORS)

    assert isinstance(plan, Act)
    assert (plan.step, plan.rerun) == (step, False)


async def test_an_action_slower_than_the_timeout_times_out() -> None:
    class SlowOps(SimulatedOps):
        async def restart_service(self, service: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed:
            await asyncio.sleep(10)
            return StepSucceeded("late")

    step = make_step(action="restart_service", service="s")
    job = make_job(step, approved=True)
    plan = plan_step(job, MAX_ERRORS)
    assert isinstance(plan, Act)

    outcome = await run_action(job, plan, KEY, Integrations(http=FakeHttp(), ops=SlowOps()), 0.01)

    assert outcome == StepTimedOut(0.01)


async def test_simulated_ops_acts_once_per_idempotency_key() -> None:
    ops = SimulatedOps()

    first = await ops.restart_service("api", KEY)
    again = await ops.restart_service("api", KEY)
    other = await ops.restart_service("api", uuid.uuid4())

    assert first == again == other
    assert len(ops.performed) == 2


async def test_httpx_client_passes_status_elapsed_and_the_idempotency_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await HttpxClient(client).request("POST", "http://x/hook", {"a": 1}, KEY)

    assert result.status == 503
    assert result.elapsed_ms >= 0
    assert seen[0].method == "POST"
    assert seen[0].content == b'{"a":1}'
    assert seen[0].headers[IDEMPOTENCY_HEADER] == str(KEY)


async def test_httpx_client_maps_a_transport_error_to_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HttpError, match="timed out"):
            await HttpxClient(client).request("GET", "http://x", None, KEY)


@dataclass
class RecordingOps(SimulatedOps):
    retried: list[str] = field(default_factory=list)

    async def retry_workflow(self, workflow_id: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed:
        self.retried.append(workflow_id)
        return await super().retry_workflow(workflow_id, idempotency_key)


RETRY = make_step(action="retry_workflow", workflowId="{{workflowId}}")
LATER = ACTED_AT + timedelta(seconds=3)


def watched(occurrences: int, last_seen_at: datetime = LATER, step: Step = RETRY) -> StepJob:
    return make_job(
        step,
        StepStatus.SUCCEEDED,
        attempts=1,
        occurrences=occurrences,
        occurrences_at_run=3,
        last_seen_at=last_seen_at,
        acted_at=ACTED_AT,
    )


async def test_a_watched_retry_without_a_new_occurrence_is_only_watched() -> None:
    ops = RecordingOps()

    assert await run(watched(occurrences=3), ops=ops) == RetryWatched()
    assert ops.retried == []


async def test_a_watched_retry_with_a_new_occurrence_failed_and_runs_again() -> None:
    ops = RecordingOps()

    outcome = await run(watched(occurrences=4), ops=ops)

    assert outcome == RetryFailed(rerun=StepSucceeded("Simulated: retry of workflow wf-9 accepted"))
    assert ops.retried == ["wf-9"]


async def test_occurrences_received_before_the_attempt_only_move_the_baseline() -> None:
    ops = RecordingOps()

    outcome = await run(watched(occurrences=5, last_seen_at=ACTED_AT), ops=ops)

    assert outcome == RetryWatched(baseline=5)
    assert ops.retried == []


async def test_a_watched_retry_carries_a_failed_rerun() -> None:
    class FailingOps(SimulatedOps):
        async def retry_workflow(self, workflow_id: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed:
            return StepFailed("workflow engine down")

    outcome = await run(watched(occurrences=4), ops=FailingOps())

    assert outcome == RetryFailed(rerun=StepFailed("workflow engine down"))


async def test_a_watched_retry_runs_again_without_a_new_approval() -> None:
    ops = RecordingOps()
    step = make_step(action="retry_workflow", workflowId="{{workflowId}}", approval="required")

    outcome = await run(watched(occurrences=4, step=step), ops=ops)

    assert isinstance(outcome, RetryFailed)
    assert ops.retried == ["wf-9"]


async def test_a_resumed_rerun_of_a_watched_retry_is_still_a_rerun() -> None:
    job = make_job(RETRY, StepStatus.RUNNING, occurrences=4, occurrences_at_run=3, attempt_key=KEY, acted_at=ACTED_AT)

    assert isinstance(await run(job), RetryFailed)
