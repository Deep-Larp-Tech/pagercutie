import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import httpx
import pytest
from pydantic import JsonValue, TypeAdapter

from pagercutie.alerts.schemas import StepDecisionKind, StepStatus
from pagercutie.pipeline.executor.actions import (
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
    GuardPending,
    RetryFailed,
    RetryWatched,
    StepFailed,
    StepOutcome,
    StepSkipped,
    StepSucceeded,
    WaitScheduled,
)
from pagercutie.pipeline.executor.stage import StepJob, run_step
from pagercutie.rules.evaluator import EventView
from pagercutie.runbooks.steps import Step

pytestmark = pytest.mark.anyio

STEP = TypeAdapter(Step)
EVENT: EventView = {
    "source": "billing",
    "schema": "workflow_failed",
    "payload": {"workflowId": "wf-9"},
}


@dataclass
class FakeHttp:
    result: HttpResult | HttpError = field(default_factory=lambda: HttpResult(status=200, elapsed_ms=35))
    calls: list[tuple[str, str, JsonValue | None]] = field(default_factory=list)

    async def request(self, method: Literal["GET", "POST", "PUT"], url: str, json: JsonValue | None) -> HttpResult:
        self.calls.append((method, url, json))
        if isinstance(self.result, HttpError):
            raise self.result
        return self.result


def make_step(**step: JsonValue) -> Step:
    return STEP.validate_python(step)


def make_job(
    step: Step,
    status: StepStatus = StepStatus.PENDING,
    decision: StepDecisionKind | None = None,
    attempts: int = 0,
    failures: dict[int, int] | None = None,
    occurrences: int = 1,
    occurrences_at_run: int | None = None,
) -> StepJob:
    return StepJob(
        run_id=uuid.uuid4(),
        index=1,
        alert_id=uuid.uuid4(),
        team_id=None,
        step=step,
        status=status,
        decision=decision,
        attempts=attempts,
        failures_by_index=failures or {},
        occurrences=occurrences,
        occurrences_at_run=occurrences_at_run,
        event=EVENT,
        lease=datetime(2026, 11, 21, tzinfo=UTC),
    )


async def run(job: StepJob, http: FakeHttp | None = None) -> StepOutcome:
    return await run_step(job, Integrations(http=http or FakeHttp(), ops=SimulatedOps()))


async def test_http_get_renders_the_url_and_reports_status_and_time() -> None:
    http = FakeHttp()

    outcome = await run(make_job(make_step(action="http_get", url="http://x/{{workflowId}}/{{schema}}")), http)

    assert outcome == StepSucceeded("HTTP 200 in 35 ms")
    assert http.calls == [("GET", "http://x/wf-9/workflow_failed", None)]


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
    job = make_job(step, StepStatus.AWAITING_APPROVAL, StepDecisionKind.APPROVE)

    outcome = await run(job, http)

    assert outcome == StepSucceeded("HTTP 200 in 35 ms")
    assert http.calls == [("POST", "http://x/wf-9", dict(EVENT))]


async def test_call_webhook_get_sends_no_body() -> None:
    http = FakeHttp()
    step = make_step(action="call_webhook", url="http://x", method="GET")

    await run(make_job(step, StepStatus.AWAITING_APPROVAL, StepDecisionKind.APPROVE), http)

    assert http.calls == [("GET", "http://x", None)]


async def test_call_webhook_put_sends_the_event_view() -> None:
    http = FakeHttp()
    step = make_step(action="call_webhook", url="http://x", method="PUT")

    await run(make_job(step, StepStatus.AWAITING_APPROVAL, StepDecisionKind.APPROVE), http)

    assert http.calls == [("PUT", "http://x", dict(EVENT))]


async def test_retry_workflow_renders_the_workflow_id() -> None:
    outcome = await run(make_job(make_step(action="retry_workflow", workflowId="{{workflowId}}")))

    assert outcome == StepSucceeded("Simulated: retry of workflow wf-9 accepted")


async def test_restart_service_renders_the_service_after_approval() -> None:
    step = make_step(action="restart_service", service="{{source}}-api")
    job = make_job(step, StepStatus.AWAITING_APPROVAL, StepDecisionKind.APPROVE)

    assert await run(job) == StepSucceeded("Simulated: restart of service billing-api accepted")


async def test_open_ticket_renders_the_title() -> None:
    outcome = await run(make_job(make_step(action="open_ticket", title="Failed {{payload.workflowId}}")))

    assert outcome == StepSucceeded("Simulated: ticket 'Failed wf-9' opened")


async def test_wait_is_scheduled_first_and_succeeds_on_the_next_claim() -> None:
    step = make_step(action="wait", seconds=30)

    assert await run(make_job(step, attempts=0)) == WaitScheduled(30)
    assert await run(make_job(step, attempts=1)) == StepSucceeded("Waited 30 s")


async def test_escalate_fails_after_approval_until_it_is_implemented() -> None:
    step = make_step(action="escalate", team="support")
    job = make_job(step, StepStatus.AWAITING_APPROVAL, StepDecisionKind.APPROVE)

    assert await run(job) == StepFailed("Escalation is not available yet")


async def test_a_step_that_needs_approval_waits_for_it() -> None:
    step = make_step(action="restart_service", service="s")

    assert await run(make_job(step)) == AwaitingApproval()


async def test_reject_skips_the_step() -> None:
    step = make_step(action="restart_service", service="s")
    job = make_job(step, StepStatus.AWAITING_APPROVAL, StepDecisionKind.REJECT)

    assert await run(job) == StepSkipped()


async def test_a_question_guard_asks_its_text() -> None:
    step = make_step(action="open_ticket", title="t", **{"if": "retry fails twice"})

    assert await run(make_job(step)) == AwaitingAnswer(question="retry fails twice")


async def test_yes_continues_to_the_action() -> None:
    step = make_step(action="open_ticket", title="t", **{"if": "is it bad?"})
    job = make_job(step, StepStatus.AWAITING_ANSWER, StepDecisionKind.YES)

    assert await run(job) == StepSucceeded("Simulated: ticket 't' opened")


async def test_yes_continues_to_the_approval_gate() -> None:
    step = make_step(action="restart_service", service="s", **{"if": "is it bad?"})
    job = make_job(step, StepStatus.AWAITING_ANSWER, StepDecisionKind.YES)

    assert await run(job) == AwaitingApproval()


async def test_no_skips_the_step() -> None:
    step = make_step(action="open_ticket", title="t", **{"if": "is it bad?"})
    job = make_job(step, StepStatus.AWAITING_ANSWER, StepDecisionKind.NO)

    assert await run(job) == StepSkipped()


async def test_a_decision_for_another_status_is_ignored() -> None:
    step = make_step(action="open_ticket", title="t", **{"if": "is it bad?"})
    job = make_job(step, StepStatus.PENDING, StepDecisionKind.NO)

    assert await run(job) == AwaitingAnswer(question="is it bad?")


@pytest.mark.parametrize(
    ("failures", "expected"), [(1, GuardPending()), (2, StepSucceeded("Simulated: ticket 't' opened"))]
)
async def test_a_failures_guard_holds_the_step_until_the_threshold(failures: int, expected: StepOutcome) -> None:
    guard: JsonValue = {"step": 0, "failures_gte": 2}
    step = make_step(action="open_ticket", title="t", **{"if": guard})

    assert await run(make_job(step, failures={0: failures})) == expected


async def test_a_manual_step_waits_until_it_is_done() -> None:
    step = make_step(action="manual", text="check the logs")

    assert await run(make_job(step)) == AwaitingManual()
    done = make_job(step, StepStatus.AWAITING_MANUAL, StepDecisionKind.DONE)
    assert await run(done) == StepSucceeded("Done")


async def test_httpx_client_passes_status_and_elapsed_through() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await HttpxClient(client).request("POST", "http://x/hook", {"a": 1})

    assert result.status == 503
    assert result.elapsed_ms >= 0
    assert seen[0].method == "POST"
    assert seen[0].content == b'{"a":1}'


async def test_httpx_client_maps_a_transport_error_to_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HttpError, match="timed out"):
            await HttpxClient(client).request("GET", "http://x", None)


@dataclass
class RecordingOps(SimulatedOps):
    retried: list[str] = field(default_factory=list)

    async def retry_workflow(self, workflow_id: str) -> StepSucceeded | StepFailed:
        self.retried.append(workflow_id)
        return await super().retry_workflow(workflow_id)


RETRY = make_step(action="retry_workflow", workflowId="{{workflowId}}")


async def test_a_watched_retry_without_a_new_occurrence_is_only_watched() -> None:
    ops = RecordingOps()
    job = make_job(RETRY, StepStatus.SUCCEEDED, attempts=1, occurrences=3, occurrences_at_run=3)

    outcome = await run_step(job, Integrations(http=FakeHttp(), ops=ops))

    assert outcome == RetryWatched()
    assert ops.retried == []


async def test_a_watched_retry_with_a_new_occurrence_failed_and_runs_again() -> None:
    ops = RecordingOps()
    job = make_job(RETRY, StepStatus.SUCCEEDED, attempts=1, occurrences=4, occurrences_at_run=3)

    outcome = await run_step(job, Integrations(http=FakeHttp(), ops=ops))

    assert outcome == RetryFailed(rerun=StepSucceeded("Simulated: retry of workflow wf-9 accepted"))
    assert ops.retried == ["wf-9"]


async def test_a_watched_retry_carries_a_failed_rerun() -> None:
    class FailingOps(SimulatedOps):
        async def retry_workflow(self, workflow_id: str) -> StepSucceeded | StepFailed:
            return StepFailed("workflow engine down")

    job = make_job(RETRY, StepStatus.SUCCEEDED, attempts=1, occurrences=4, occurrences_at_run=3)

    outcome = await run_step(job, Integrations(http=FakeHttp(), ops=FailingOps()))

    assert outcome == RetryFailed(rerun=StepFailed("workflow engine down"))


async def test_a_watched_retry_runs_again_without_a_new_approval() -> None:
    ops = RecordingOps()
    step = make_step(action="retry_workflow", workflowId="{{workflowId}}", approval="required")
    job = make_job(step, StepStatus.SUCCEEDED, attempts=1, occurrences=4, occurrences_at_run=3)

    outcome = await run_step(job, Integrations(http=FakeHttp(), ops=ops))

    assert isinstance(outcome, RetryFailed)
    assert ops.retried == ["wf-9"]
