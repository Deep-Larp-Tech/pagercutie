"""Entrypoints of the runbook executor, called by the orchestrator (`start_run`) and its loop (`worker.py`).

Outcomes are in `outcomes.py` and the integrations in `actions.py`, so that `actions.py` can return outcomes without
importing this module.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, assert_never

import structlog
from pydantic import JsonValue
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, RunbookRun, StepRun
from pagercutie.alerts.schemas import AlertStatus, StepDecisionKind, StepStatus, expected_status
from pagercutie.audit.service import record_entry
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.templates import parse, render
from pagercutie.pipeline.executor.actions import HttpError, Integrations
from pagercutie.pipeline.executor.gates import clearance, step_gates
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

# How long a claimed step run stays invisible to other replicas; `run_at` is moved this far ahead (ADR-0008).
LEASE = timedelta(seconds=30)


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
    # The `run_at` the claim wrote; `complete_step` writes only while the step run still holds this lease.
    lease: datetime

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
    """Claim up to `limit` step runs whose `run_at` has passed, with `FOR UPDATE SKIP LOCKED`, oldest first.

    The lease is `run_at` moved to `now + LEASE`; `status` and `decision` stay as they are, because they give the
    step's clearance (ADR-0079). A replica that dies mid-step lets the lease expire and another claims the step
    again (ADR-0008). The caller commits.
    Steps of resolved alerts are parked (`run_at` set to null) instead of claimed.
    """
    # Closing runs on resolve is not implemented, so the executor parks the steps of resolved alerts: with `run_at`
    # null they leave the partial index instead of being scanned on every poll.
    await session.execute(
        update(StepRun)
        .where(
            StepRun.run_at <= now,
            StepRun.run_id.in_(
                select(RunbookRun.id)
                .join(Alert, Alert.id == RunbookRun.alert_id)
                .where(Alert.status == AlertStatus.RESOLVED)
            ),
        )
        .values(run_at=None)
    )
    rows = (
        await session.execute(
            select(StepRun, RunbookRun.alert_id, Alert.team_id, Alert.occurrences, RunbookRun.event)
            .join(RunbookRun, RunbookRun.id == StepRun.run_id)
            .join(Alert, Alert.id == RunbookRun.alert_id)
            .where(StepRun.run_at.is_not(None), StepRun.run_at <= now, Alert.status != AlertStatus.RESOLVED)
            .order_by(StepRun.run_at)
            .limit(limit)
            .with_for_update(of=StepRun, skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).all()
    if not rows:
        return []
    failures: dict[uuid.UUID, dict[int, int]] = {}
    run_ids = {row[0].run_id for row in rows}
    for run_id, index, count in await session.execute(
        select(StepRun.run_id, StepRun.index, StepRun.failures).where(StepRun.run_id.in_(run_ids))
    ):
        failures.setdefault(run_id, {})[index] = count
    jobs = [
        StepJob(
            run_id=step_run.run_id,
            index=step_run.index,
            alert_id=alert_id,
            team_id=team_id,
            step=step_run.step,
            status=step_run.status,
            decision=step_run.decision,
            attempts=step_run.attempts,
            failures_by_index=failures[step_run.run_id],
            occurrences=occurrences,
            occurrences_at_run=step_run.occurrences_at_run,
            event=event,
            lease=now + LEASE,
        )
        for step_run, alert_id, team_id, occurrences, event in rows
    ]
    for step_run, *_ in rows:
        step_run.run_at = now + LEASE
    await session.flush()
    return jobs


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


@dataclass(frozen=True)
class _Change:
    """What an outcome writes to the step run."""

    status: StepStatus
    audit: str | None
    # None leaves `result` as it is.
    result: str | None = None
    attempted: bool = False
    failed: bool = False
    run_at: datetime | None = None
    # The step is done, so the run goes on to its next step.
    finished: bool = False


def _change(job: StepJob, outcome: StepOutcome, now: datetime) -> _Change:
    """Map `outcome` to the step run's new row (SPEC §11.3); audited only when the status changes."""

    def audit(status: StepStatus) -> str | None:
        return f"step_run.{status}" if status is not job.status else None

    match outcome:
        case StepSucceeded(result=result):
            return _Change(StepStatus.SUCCEEDED, audit(StepStatus.SUCCEEDED), result, attempted=True, finished=True)
        case StepFailed(error=error):
            return _Change(
                StepStatus.FAILED, audit(StepStatus.FAILED), error, attempted=True, failed=True, finished=True
            )
        case StepSkipped():
            return _Change(StepStatus.SKIPPED, audit(StepStatus.SKIPPED), finished=True)
        case AwaitingApproval():
            return _Change(StepStatus.AWAITING_APPROVAL, audit(StepStatus.AWAITING_APPROVAL))
        case AwaitingAnswer(question=question):
            return _Change(StepStatus.AWAITING_ANSWER, audit(StepStatus.AWAITING_ANSWER), question)
        case AwaitingManual():
            return _Change(StepStatus.AWAITING_MANUAL, audit(StepStatus.AWAITING_MANUAL))
        case GuardPending():
            return _Change(StepStatus.PENDING, audit(StepStatus.PENDING))
        case WaitScheduled(seconds=seconds):
            # `running` means every gate was passed (`gates.clearance`), so the claim after the delay succeeds.
            return _Change(
                StepStatus.RUNNING,
                "step_run.wait_started",
                f"Waiting {seconds} s",
                attempted=True,
                run_at=now + timedelta(seconds=seconds),
            )
        case _:
            assert_never(outcome)


async def complete_step(session: AsyncSession, job: StepJob, outcome: StepOutcome, now: datetime) -> None:
    """Store the outcome, audit it (RUN-5) and schedule the next step.

    Writes only while the step run still holds the lease and has the `status` and `decision` it was claimed with.
    Otherwise the outcome is late (the lease expired and another replica claimed the step) or a person decided in
    the meantime; it is dropped and the step is checked again by whoever claims it next.
    The caller commits.
    """
    change = _change(job, outcome, now)
    written = await session.scalar(
        update(StepRun)
        .where(
            StepRun.run_id == job.run_id,
            StepRun.index == job.index,
            StepRun.run_at == job.lease,
            StepRun.status == job.status,
            StepRun.decision.is_not_distinct_from(job.decision),
        )
        .values(
            status=change.status,
            run_at=change.run_at,
            result=change.result if change.result is not None else StepRun.result,
            attempts=StepRun.attempts + (1 if change.attempted else 0),
            failures=StepRun.failures + (1 if change.failed else 0),
        )
        .returning(StepRun.index)
    )
    if written is None:
        _log.warning(
            "executor.step_outcome_stale",
            run_id=str(job.run_id),
            index=job.index,
            outcome=type(outcome).__name__,
        )
        return
    if change.audit is not None:
        record_entry(
            session,
            actor_user_id=None,
            action=change.audit,
            entity_type="runbook_run",
            entity_id=job.run_id,
            team_id=job.team_id,
            data={"index": job.index, "status": change.status, "result": change.result},
        )
    if change.finished:
        await _advance(session, job, now)


async def _advance(session: AsyncSession, job: StepJob, now: datetime) -> None:
    """After a step finished: run the next pending step, or finish the run when no step is unfinished.

    Steps run in index order, so a guarded step is checked again whenever the run reaches it (SPEC §11.4).
    """
    steps = (
        await session.execute(
            select(StepRun.index, StepRun.status).where(StepRun.run_id == job.run_id).order_by(StepRun.index)
        )
    ).all()
    next_index = next((i for i, status in steps if i > job.index and status is StepStatus.PENDING), None)
    if next_index is not None:
        await session.execute(
            update(StepRun).where(StepRun.run_id == job.run_id, StepRun.index == next_index).values(run_at=now)
        )
        await notify(session, NotifyChannel.STEPS_PENDING)
    elif all(status in _FINAL for _, status in steps):
        record_entry(
            session,
            actor_user_id=None,
            action="runbook_run.finished",
            entity_type="runbook_run",
            entity_id=job.run_id,
            team_id=job.team_id,
            data={"steps": len(steps)},
        )


_FINAL = frozenset({StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED})
