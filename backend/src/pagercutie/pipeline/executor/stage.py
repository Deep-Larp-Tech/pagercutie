"""Entrypoints of the runbook executor, called by the orchestrator (`start_run`) and its loop (`worker.py`).

Outcomes are in `outcomes.py` and the integrations in `actions.py`, so that `actions.py` can return outcomes without
importing this module.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, assert_never

import structlog
from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, RunbookRun, StepRun
from pagercutie.alerts.schemas import StepDecisionKind, StepStatus
from pagercutie.audit.service import record_entry
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.templates import parse, render
from pagercutie.pipeline.executor.actions import HttpError, Integrations
from pagercutie.pipeline.executor.gates import clearance, expected_status, step_gates
from pagercutie.pipeline.executor.outcomes import (
    AwaitingAnswer,
    AwaitingApproval,
    AwaitingManual,
    GuardPending,
    StepFailed,
    StepOutcome,
    StepSkipped,
    StepSucceeded,
    WaitScheduled,
)
from pagercutie.pipeline.messages import Opened
from pagercutie.rules import evaluator
from pagercutie.rules.evaluator import EventView, template_resolver
from pagercutie.runbooks.models import Runbook
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

_log = structlog.get_logger("executor")


@dataclass(frozen=True)
class StepJob:
    """A runnable step run claimed by `claim_due_steps`."""

    run_id: uuid.UUID
    index: int
    alert_id: uuid.UUID
    # The alert's team, for audit entries.
    team_id: uuid.UUID | None
    step: Step
    # Where the step waits; with `decision` it gives `gates.clearance`.
    status: StepStatus
    decision: StepDecisionKind | None
    attempts: int
    # Failures of every step in the run, for `FailuresGuard`.
    failures_by_index: Mapping[int, int]
    # The alert's current count.
    occurrences: int
    occurrences_at_run: int | None
    # The run's stored event view, for rendering the step's templates (SPEC §11.2).
    event: EventView

    def failures(self, index: int) -> int:
        """How many times step `index` has failed in this run; 0 when it has not (`gates.RunState`)."""
        return self.failures_by_index.get(index, 0)


async def start_run(session: AsyncSession, opened: Opened) -> uuid.UUID | None:
    """Create the runbook run and its step runs for a new alert and return the run's ID (SPEC §11.3).

    Returns None, writing nothing, when no runbook applies: the rule links none and no runbook of the alert's team
    attaches to the event, the linked runbook no longer exists, or it has no steps.
    Idempotent on the alert (ADR-0008): when the alert already has a run, returns its ID without inserting steps,
    auditing or notifying again. Runs in the caller's transaction.
    """
    alert_id = opened.alert_id
    view = _view(opened)
    runbook = await _pick_runbook(session, opened, view)
    if runbook is None or not runbook.steps:
        return None
    run_id = await session.scalar(
        insert(RunbookRun)
        .values(
            id=uuid.uuid7(),
            alert_id=alert_id,
            runbook_id=runbook.id,
            event=view,
        )
        .on_conflict_do_nothing(index_elements=[RunbookRun.alert_id])
        .returning(RunbookRun.id)
    )
    if run_id is None:
        return await session.scalar(select(RunbookRun.id).where(RunbookRun.alert_id == alert_id))
    # Steps run in index order; completing a step schedules the next one.
    await session.execute(
        insert(StepRun).values(
            [
                {
                    "run_id": run_id,
                    "index": index,
                    "step": step,
                    "status": StepStatus.PENDING,
                    "attempts": 0,
                    "failures": 0,
                    "run_at": func.now() if index == 0 else None,
                }
                for index, step in enumerate(runbook.steps)
            ]
        )
    )
    team_id = await session.scalar(select(Alert.team_id).where(Alert.id == alert_id))
    record_entry(
        session,
        actor_user_id=None,
        action="runbook_run.started",
        entity_type="runbook_run",
        entity_id=run_id,
        team_id=team_id,
        data={"alert_id": str(alert_id), "runbook_id": str(runbook.id), "steps": len(runbook.steps)},
    )
    await notify(session, NotifyChannel.STEPS_PENDING)
    return run_id


def _view(opened: Opened) -> EventView:
    event = opened.match.event
    return evaluator.event_view(
        source=event.source,
        schema=event.schema_name,
        schema_id=event.schema_id,
        severity=event.severity,
        payload=event.payload,
    )


async def _pick_runbook(session: AsyncSession, opened: Opened, view: EventView) -> Runbook | None:
    """The rule's linked runbook; with no link, the oldest runbook of the alert's team whose `attach` matches `view`.

    A personal rule has no team, so it only has the link (RUN-1, ADR-0080).
    """
    runbook_id = opened.match.rule.runbook_id
    if runbook_id is not None:
        runbook = await session.get(Runbook, runbook_id)
        if runbook is None:
            # The rule is a cached snapshot, so it can still name a runbook that was unlinked or deleted since.
            _log.warning("executor.runbook_missing", alert_id=str(opened.alert_id), runbook_id=str(runbook_id))
        return runbook
    team_id = await session.scalar(select(Alert.team_id).where(Alert.id == opened.alert_id))
    if team_id is None:
        return None
    candidates = await session.scalars(
        select(Runbook)
        .where(Runbook.team_id == team_id, Runbook.attach.is_not(None))
        .order_by(Runbook.created_at, Runbook.id)
    )
    for runbook in candidates:
        if runbook.attach is not None and evaluator.compile_condition(runbook.attach)(view):
            return runbook
    return None


async def claim_due_steps(session: AsyncSession, limit: int, now: datetime) -> list[StepJob]:
    """Claim up to `limit` step runs whose `run_at` has passed, with `FOR UPDATE SKIP LOCKED`."""
    raise NotImplementedYet("Step claiming")


async def run_step(job: StepJob, integrations: Integrations) -> StepOutcome:
    """Check the gates, then run the step's action through `integrations`. Runs outside any transaction.

    Returns the outcome for every expected failure (a non-2xx response, an unreachable URL). Any other exception from
    an integration propagates, so the loop can log it and let the lease expire, which runs the step again (ADR-0008).
    """
    if job.decision in (StepDecisionKind.REJECT, StepDecisionKind.NO) and expected_status(job.decision) is job.status:
        return StepSkipped()
    waiting = step_gates(job.step).waiting_for(clearance(job.status, job.decision), job)
    match waiting:
        case None:
            return await _act(job, integrations)
        case StepStatus.PENDING:
            return GuardPending()
        case StepStatus.AWAITING_APPROVAL:
            return AwaitingApproval()
        case StepStatus.AWAITING_ANSWER:
            # Only an unparsed guard waits for an answer, and it is the step's `if` text.
            question = job.step.if_
            return AwaitingAnswer(question=question if isinstance(question, str) else "")
        case StepStatus.AWAITING_MANUAL:
            return AwaitingManual()
        case _:
            assert_never(waiting)


def _render(job: StepJob, value: str) -> str:
    return render(parse(value), template_resolver(job.event))


async def _act(job: StepJob, integrations: Integrations) -> StepOutcome:
    step = job.step
    match step:
        case HttpGet():
            return await _request(integrations, "GET", _render(job, step.url), None)
        case CallWebhook():
            body = None if step.method == "GET" else dict(job.event)
            return await _request(integrations, step.method, _render(job, step.url), body)
        case RetryWorkflow():
            return await integrations.ops.retry_workflow(_render(job, step.workflow_id))
        case RestartService():
            return await integrations.ops.restart_service(_render(job, step.service))
        case OpenTicket():
            return await integrations.ops.open_ticket(_render(job, step.title))
        case Wait():
            # Scheduling counts as the first attempt, so the claim after the delay finishes the step.
            if job.attempts == 0:
                return WaitScheduled(step.seconds)
            return StepSucceeded(f"Waited {step.seconds} s")
        case Manual():
            # The manual gate opens only after `done`.
            return StepSucceeded("Done")
        case Escalate():
            # Replaced by the escalation of SPEC §11.4 step 5.
            return StepFailed("Escalation is not available yet")
        case _:
            assert_never(step)


async def _request(
    integrations: Integrations, method: Literal["GET", "POST", "PUT"], url: str, body: JsonValue | None
) -> StepSucceeded | StepFailed:
    try:
        response = await integrations.http.request(method, url, body)
    except HttpError as error:
        return StepFailed(f"Request failed: {error}")
    text = f"HTTP {response.status} in {response.elapsed_ms} ms"
    return StepSucceeded(text) if 200 <= response.status < 300 else StepFailed(text)


async def complete_step(session: AsyncSession, job: StepJob, outcome: StepOutcome) -> None:
    """Store the outcome, audit it (RUN-5) and schedule the next step."""
    raise NotImplementedYet("Step completion")
