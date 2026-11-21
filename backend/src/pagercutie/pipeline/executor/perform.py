"""Deciding what a claimed step does (`plan_step`, pure) and running its action (`run_action`) (SPEC §11.2-§11.4)."""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal, assert_never

from pydantic import JsonValue

from pagercutie.alerts.schemas import StepStatus
from pagercutie.core.templates import parse, render
from pagercutie.pipeline.executor.actions import HttpError, Integrations
from pagercutie.pipeline.executor.claims import StepJob
from pagercutie.pipeline.executor.gates import Clearance, step_gates
from pagercutie.pipeline.executor.outcomes import (
    ActionResult,
    AwaitingManual,
    EscalationDue,
    GaveUp,
    RetryFailed,
    RetryWatched,
    StepFailed,
    StepOutcome,
    StepSucceeded,
    StepTimedOut,
    WaitScheduled,
)
from pagercutie.rules.evaluator import template_resolver
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

type ActionStep = HttpGet | CallWebhook | RetryWorkflow | RestartService | OpenTicket
"""Steps that act through an integration, so they run `running` with an idempotency key (ADR-0103)."""


@dataclass(frozen=True)
class Act:
    """Run the step's action: mark the step `running` (`claims.start_step`), then `run_action`."""

    step: ActionStep
    # A watched retry whose attempt failed: its result is wrapped in `RetryFailed` (SPEC §11.4).
    rerun: bool


@dataclass(frozen=True)
class Settle:
    """No integration is called; `complete_step` writes `outcome`."""

    outcome: StepOutcome


type Plan = Act | Settle
"""What a claimed step does next."""


def plan_step(job: StepJob, max_errors: int) -> Plan:
    """Decide what the claimed step does, from its row and the run's state alone.

    In order: a step whose claims ended without an outcome `max_errors` times gives up (ADR-0103); a `running` step
    resumes (`_resume`); a succeeded retry is watched (`_watch`); otherwise the gates are checked (guard, approval) and
    the step acts, waits or asks for a person.
    """
    if job.errors >= max_errors:
        return Settle(GaveUp(job.errors))
    step = job.step
    if job.status is StepStatus.RUNNING:
        return _resume(job, step)
    if isinstance(step, RetryWorkflow) and job.status is StepStatus.SUCCEEDED and job.occurrences_at_run is not None:
        # Its gates were passed when it first ran: an approval covers the step's re-runs.
        return _watch(job, step, job.occurrences_at_run)
    held = step_gates(step).check(Clearance(guard_answered=job.guard_answered, approved=job.approved), job)
    if held is not None:
        return Settle(held)
    match step:
        case HttpGet() | CallWebhook() | RetryWorkflow() | RestartService() | OpenTicket():
            return Act(step, rerun=False)
        case Wait():
            return Settle(WaitScheduled(step.seconds))
        case Escalate():
            return Settle(EscalationDue(step.team))
        case Manual():
            # The decision endpoint marks it `succeeded` on `done`, so the executor only ever sees it unticked.
            return Settle(AwaitingManual())
        case _:
            assert_never(step)


def _resume(job: StepJob, step: Step) -> Plan:
    """A `running` step: a `wait` whose delay ended, or an action whose replica was lost before its outcome was written,
    which runs again with the same idempotency key (ADR-0103)."""
    match step:
        case Wait():
            return Settle(StepSucceeded(f"Waited {step.seconds} s"))
        case RetryWorkflow():
            # Only a watched retry's re-run is `running` with a baseline.
            return Act(step, rerun=job.occurrences_at_run is not None)
        case HttpGet() | CallWebhook() | RestartService() | OpenTicket():
            return Act(step, rerun=False)
        case Escalate():
            return Settle(EscalationDue(step.team))
        case Manual():
            return Settle(AwaitingManual())
        case _:
            assert_never(step)


def _watch(job: StepJob, step: RetryWorkflow, baseline: int) -> Plan:
    """Compare the alert's occurrences with the retry's baseline (ADR-0020).

    A higher count fails the attempt only when an occurrence was received after the attempt started; occurrences
    received earlier reached the count late (the counter flush, SPEC §5.2) and only move the baseline (SPEC §11.4).
    """
    if job.occurrences <= baseline:
        return Settle(RetryWatched())
    if job.acted_at is not None and job.last_seen_at <= job.acted_at:
        return Settle(RetryWatched(baseline=job.occurrences))
    return Act(step, rerun=True)


async def run_action(
    job: StepJob, act: Act, key: uuid.UUID, integrations: Integrations, timeout_seconds: float
) -> StepOutcome:
    """Run the action of a `running` step through `integrations` with the idempotency key `key`. Runs outside any
    transaction.

    An action slower than `timeout_seconds` yields `StepTimedOut`. Returns the outcome for every expected failure (a
    non-2xx response, an unreachable URL). Any other exception propagates, so the loop can log it and let the lease
    expire, and the next claim counts it in `errors` (ADR-0103).
    """
    result: ActionResult
    try:
        async with asyncio.timeout(timeout_seconds):
            result = await _act(job, act.step, key, integrations)
    except TimeoutError:
        result = StepTimedOut(timeout_seconds)
    return RetryFailed(rerun=result) if act.rerun else result


def _render(job: StepJob, value: str) -> str:
    return render(parse(value), template_resolver(job.event))


async def _act(
    job: StepJob, step: ActionStep, key: uuid.UUID, integrations: Integrations
) -> StepSucceeded | StepFailed:
    match step:
        case HttpGet():
            return await _request(integrations, "GET", _render(job, step.url), None, key)
        case CallWebhook():
            body = None if step.method == "GET" else dict(job.event)
            return await _request(integrations, step.method, _render(job, step.url), body, key)
        case RetryWorkflow():
            return await integrations.ops.retry_workflow(_render(job, step.workflow_id), key)
        case RestartService():
            return await integrations.ops.restart_service(_render(job, step.service), key)
        case OpenTicket():
            return await integrations.ops.open_ticket(_render(job, step.title), key)
        case _:
            assert_never(step)


async def _request(
    integrations: Integrations,
    method: Literal["GET", "POST", "PUT"],
    url: str,
    body: JsonValue | None,
    key: uuid.UUID,
) -> StepSucceeded | StepFailed:
    try:
        response = await integrations.http.request(method, url, body, key)
    except HttpError as error:
        return StepFailed(f"Request failed: {error}")
    text = f"HTTP {response.status} in {response.elapsed_ms} ms"
    return StepSucceeded(text) if 200 <= response.status < 300 else StepFailed(text)
