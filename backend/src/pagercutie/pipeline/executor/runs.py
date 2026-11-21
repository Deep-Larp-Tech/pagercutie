"""Runbook selection and run creation for a new alert (SPEC §11.1, §11.3)."""

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import RunbookRun, StepRun
from pagercutie.alerts.schemas import StepStatus
from pagercutie.alerts.service import notify_alert_changed
from pagercutie.audit.schemas import AuditAction
from pagercutie.audit.service import record
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.pipeline.messages import Opened
from pagercutie.pipeline.recipients import current_traceparent
from pagercutie.rules import evaluator
from pagercutie.rules.evaluator import EventView
from pagercutie.runbooks.models import Runbook

_log = structlog.get_logger("executor")


async def start_run(session: AsyncSession, opened: Opened) -> uuid.UUID | None:
    """Create the runbook run and its step runs for a new alert and return the run's ID (SPEC §11.3).

    Returns None, writing nothing, when no runbook applies: the rule links none and no runbook of the alert's team
    attaches to the event, the linked runbook no longer exists, or it has no steps.
    Idempotent on the alert (ADR-0008): when the alert already has a run, returns its ID without inserting steps,
    auditing or notifying again. Each step run stores the current span's trace context, so step spans link to the
    ingest request (SPEC §13). Runs in the caller's transaction.
    """
    alert_id = opened.alert_id
    view = opened.match.event.view()
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
    traceparent = current_traceparent()
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
                    "errors": 0,
                    "run_at": func.now() if index == 0 else None,
                    "traceparent": traceparent,
                }
                for index, step in enumerate(runbook.steps)
            ]
        )
    )
    record(
        session,
        None,
        AuditAction.RUNBOOK_RUN_STARTED,
        alert_id,
        opened.team_id,
        {"run_id": str(run_id), "runbook_id": str(runbook.id), "steps": len(runbook.steps)},
    )
    await notify(session, NotifyChannel.STEPS_PENDING)
    # An open alert detail loaded before the run existed reloads it from this event.
    await notify_alert_changed(session, alert_id, "alert.updated")
    return run_id


async def _pick_runbook(session: AsyncSession, opened: Opened, view: EventView) -> Runbook | None:
    """The rule's linked runbook; with no link, the oldest runbook of the alert's team whose `attach` matches `view`.

    A personal rule has no team, so it only has the link (RUN-1, ADR-0089). Deleted runbooks start no runs (ADR-0068).
    """
    runbook_id = opened.match.rule.runbook_id
    if runbook_id is not None:
        runbook = await session.scalar(select(Runbook).where(Runbook.id == runbook_id, Runbook.deleted_at.is_(None)))
        if runbook is None:
            # The rule is a cached snapshot, so it can still name a runbook that was unlinked or deleted since.
            _log.warning("executor.runbook_missing", alert_id=str(opened.alert_id), runbook_id=str(runbook_id))
        return runbook
    team_id = opened.team_id
    if team_id is None:
        return None
    candidates = await session.scalars(
        select(Runbook)
        .where(Runbook.team_id == team_id, Runbook.attach.is_not(None), Runbook.deleted_at.is_(None))
        .order_by(Runbook.created_at, Runbook.id)
    )
    for runbook in candidates:
        if runbook.attach is not None and evaluator.compile_condition(runbook.attach)(view):
            return runbook
    return None
