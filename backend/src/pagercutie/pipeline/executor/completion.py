"""Writing a step's outcome: the step run's row, its audit entry, an escalation, and moving the run on (SPEC §11.3)."""

from collections.abc import Mapping
from datetime import datetime
from typing import assert_never

import structlog
from pydantic import JsonValue
from sqlalchemy import case, func, null, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, StepRun
from pagercutie.alerts.runs import FINAL_STEP_STATUSES, RunContext, advance_run, lock_run
from pagercutie.alerts.schemas import StepStatus
from pagercutie.alerts.service import notify_alert_changed
from pagercutie.audit.schemas import AuditAction
from pagercutie.audit.service import record
from pagercutie.pipeline.executor import escalation
from pagercutie.pipeline.executor.claims import StepJob
from pagercutie.pipeline.executor.outcomes import EscalationDue, ResolvedOutcome, StepFailed, StepOutcome, StepSucceeded
from pagercutie.pipeline.executor.transitions import (
    WATCH_INTERVAL,
    Await,
    Delay,
    Finish,
    Hold,
    Transition,
    Watch,
    executed_action,
    transition,
)
from pagercutie.teams.models import Team

_log = structlog.get_logger("executor")


async def complete_step(session: AsyncSession, job: StepJob, outcome: StepOutcome, now: datetime) -> None:
    """Store the outcome, audit it (RUN-5), escalate for an `escalate` step and move the run on.

    Takes the run's lock first (`alerts.runs.lock_run`). Writes only while the step run still holds the claim's lease
    and has the `status`, `guard_answered` and `approved` it was claimed (or started) with. Otherwise the outcome is
    late (the lease expired and another replica claimed the step) or the step changed meanwhile (a person decided, the
    alert was resolved); it is dropped, audited with `"discarded": true` when its action ran (ADR-0107), and the step
    is checked again by whoever claims it next. The caller commits.
    """
    if isinstance(outcome, EscalationDue):
        # Escalation updates the alert row; taking it first keeps the order alert, run, steps that a resolve uses.
        await session.execute(select(Alert.id).where(Alert.id == job.alert_id).with_for_update())
    await lock_run(session, job.run_id)
    team: Team | None = None
    resolved: ResolvedOutcome
    if isinstance(outcome, EscalationDue):
        team = await escalation.find_team(session, outcome.team)
        resolved = (
            StepFailed(f"No team has the slug '{outcome.team}'")
            if team is None
            else StepSucceeded(f"Escalated to team {team.name}")
        )
    else:
        resolved = outcome
    change = transition(job, resolved, now)
    written = await session.scalar(
        update(StepRun)
        .where(
            StepRun.run_id == job.run_id,
            StepRun.index == job.index,
            StepRun.lease_until == job.lease,
            StepRun.status == job.status,
            StepRun.guard_answered == job.guard_answered,
            StepRun.approved == job.approved,
        )
        .values(await _values(session, job, change, now))
        .returning(StepRun.index)
    )
    if written is None:
        _discarded(session, job, resolved, change)
        return
    _audit(session, job, change)
    if _visible(job, change):
        # The alert detail reloads the run from this event, so a step the executor moved on shows without a reload.
        await notify_alert_changed(session, job.alert_id, "alert.updated")
    if team is not None:
        await escalation.escalate(session, job, team, now)
    if isinstance(change, Finish):
        await advance_run(session, RunContext(job.run_id, job.alert_id, job.team_id, None), job.index, now)


async def _values(session: AsyncSession, job: StepJob, change: Transition, now: datetime) -> dict[str, object]:
    """The columns `change` writes; every outcome releases the lease."""
    match change:
        case Finish():
            return {
                "status": change.status,
                "result": change.result,
                "run_at": change.watch_at,
                "lease_until": None,
                "attempts": StepRun.attempts + (1 if change.attempted else 0),
                "failures": StepRun.failures + change.failures_added,
                "occurrences_at_run": change.baseline if change.baseline is not None else StepRun.occurrences_at_run,
            }
        case Await():
            return {
                "status": change.status,
                "result": change.result if change.result is not None else StepRun.result,
                "run_at": None,
                "lease_until": None,
            }
        case Hold():
            # `advance_run` may have made the step due again while this claim checked the guard (ADR-0108).
            parked = case((StepRun.run_at.is_not_distinct_from(job.due_at), null()), else_=StepRun.run_at)
            return {"status": StepStatus.PENDING, "run_at": parked, "lease_until": None}
        case Delay():
            return {
                "status": StepStatus.RUNNING,
                "result": change.result,
                "run_at": change.until,
                "lease_until": None,
                "attempts": StepRun.attempts + 1,
            }
        case Watch():
            watching = await _has_unfinished_step(session, job)
            return {
                "run_at": now + WATCH_INTERVAL if watching else None,
                "lease_until": None,
                "occurrences_at_run": change.baseline if change.baseline is not None else StepRun.occurrences_at_run,
            }
        case _:
            assert_never(change)


def _visible(job: StepJob, change: Transition) -> bool:
    """Whether the write changes what `GET /alerts/{id}/runbook-run` shows; a watched retry's re-claim does not."""
    match change:
        case Finish() | Delay():
            return True
        case Await():
            return change.status is not job.status or change.result is not None
        case Hold():
            return job.status is not StepStatus.PENDING
        case Watch():
            return False
        case _:
            assert_never(change)


def _audit(session: AsyncSession, job: StepJob, change: Transition) -> None:
    """`step.*` for a transition (RUN-5): always for `Finish` and `Delay`, for `Await` when the status changed."""
    match change:
        case Finish():
            _record(session, job, change.audit, change.status, change.result, change.details)
        case Await():
            if change.status is not job.status:
                _record(session, job, _awaiting_action(change), change.status, change.result, {})
        case Delay():
            _record(session, job, AuditAction.STEP_STARTED, StepStatus.RUNNING, change.result, {})
        case Hold() | Watch():
            pass
        case _:
            assert_never(change)


def _discarded(session: AsyncSession, job: StepJob, outcome: ResolvedOutcome, change: Transition) -> None:
    """Log a stale outcome, and audit it when its action ran, so the audit log shows what was done (RUN-5)."""
    _log.warning("executor.step_outcome_stale", run_id=str(job.run_id), index=job.index, outcome=type(outcome).__name__)
    if executed_action(job, outcome) and isinstance(change, Finish):
        _record(
            session,
            job,
            change.audit,
            change.status,
            change.result,
            {**change.details, "discarded": True, "attempt_key": str(job.attempt_key)},
        )


def _awaiting_action(change: Await) -> AuditAction:
    match change.status:
        case StepStatus.AWAITING_APPROVAL:
            return AuditAction.STEP_AWAITING_APPROVAL
        case StepStatus.AWAITING_ANSWER:
            return AuditAction.STEP_AWAITING_ANSWER
        case StepStatus.AWAITING_MANUAL:
            return AuditAction.STEP_AWAITING_MANUAL
        case _:
            assert_never(change.status)


def _record(
    session: AsyncSession,
    job: StepJob,
    action: AuditAction,
    status: StepStatus,
    result: str | None,
    details: Mapping[str, JsonValue],
) -> None:
    data: dict[str, JsonValue] = {
        "run_id": str(job.run_id),
        "index": job.index,
        "status": status.value,
        "result": result,
    }
    data.update(details)
    record(session, None, action, job.alert_id, job.team_id, data)


async def _has_unfinished_step(session: AsyncSession, job: StepJob) -> bool:
    """Whether the run has a step that is not final, so a succeeded retry keeps watching (SPEC §11.4)."""
    count = await session.scalar(
        select(func.count())
        .select_from(StepRun)
        .where(StepRun.run_id == job.run_id, StepRun.status.not_in(FINAL_STEP_STATUSES))
    )
    return (count or 0) > 0
