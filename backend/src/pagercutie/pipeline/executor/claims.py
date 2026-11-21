"""Claiming due step runs and marking them `running` before their action (SPEC §11.3, ADR-0103).

A claim sets `lease_until`; `run_at` keeps its one meaning, when the executor looks at the step next. A claim that
finds a lease already set knows the previous claim ended without an outcome and counts it in `errors`.
"""

import dataclasses
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, RunbookRun, StepRun
from pagercutie.alerts.runs import RunContext, finish_run, is_final
from pagercutie.alerts.schemas import AlertStatus, StepStatus
from pagercutie.audit.schemas import AuditAction
from pagercutie.audit.service import record
from pagercutie.rules.evaluator import EventView
from pagercutie.runbooks.steps import RetryWorkflow, Step, Wait

_log = structlog.get_logger("executor")


@dataclass(frozen=True)
class StepJob:
    """A step run claimed by `claim_due_steps`, with what planning and completing it read."""

    run_id: uuid.UUID
    index: int
    alert_id: uuid.UUID
    # The alert's team, for audit entries.
    team_id: uuid.UUID | None
    step: Step
    # The status the step was claimed in; `complete_step` writes only while the row still has it.
    status: StepStatus
    # The gates a person cleared, set by the decision endpoint.
    guard_answered: bool
    approved: bool
    # Who cleared the last gate, for the escalation's audit entry.
    decided_by: uuid.UUID | None
    attempts: int
    # Claims of this step that ended without an outcome, this claim's predecessor included (ADR-0103).
    errors: int
    # Failures of every step in the run, for `FailuresGuard`.
    failures_by_index: Mapping[int, int]
    # Steps of the run that can still count a failure: unfinished, or a succeeded retry that is watched (ADR-0104).
    unsettled: frozenset[int]
    # The alert's current count and when its newest counted occurrence was received.
    occurrences: int
    last_seen_at: datetime
    occurrences_at_run: int | None
    # The idempotency key and start of the attempt in progress or last made; null before the first attempt.
    attempt_key: uuid.UUID | None
    acted_at: datetime | None
    # The run's stored event view, for rendering the step's templates (SPEC §11.2).
    event: EventView
    # The `run_at` the step was claimed at; a parking outcome keeps a `run_at` written since (`advance_run`).
    due_at: datetime
    # The `lease_until` the claim wrote; `start_step` and `complete_step` write only while the row still holds it.
    lease: datetime
    # W3C trace context of the request that started the run (SPEC §13).
    traceparent: str | None

    def failures(self, index: int) -> int:
        """How many times step `index` has failed in this run; 0 when it has not (`gates.RunState`)."""
        return self.failures_by_index.get(index, 0)

    def can_still_fail(self, index: int) -> bool:
        """Whether step `index` may still count a failure (`gates.RunState`); false for an index the run lacks."""
        return index in self.unsettled


def _can_still_fail(step: Step, status: StepStatus) -> bool:
    # A succeeded retry is watched while the run has an unfinished step, so it may still count a failure (SPEC §11.4).
    return not is_final(status) or (status is StepStatus.SUCCEEDED and isinstance(step, RetryWorkflow))


async def claim_due_steps(session: AsyncSession, limit: int, now: datetime, lease: timedelta) -> list[StepJob]:
    """Claim up to `limit` step runs whose `run_at` has passed and that hold no live lease, oldest first, with
    `FOR UPDATE SKIP LOCKED`, and set `lease_until = now + lease`.

    `status`, `guard_answered` and `approved` stay as they are, because they give the step's clearance (ADR-0088). A
    step whose previous lease expired gets one more `errors` (ADR-0103). Steps of resolved alerts are parked or
    finished instead of claimed (`_park_resolved`). The caller commits.
    """
    await _park_resolved(session, now)
    rows = (
        await session.execute(
            select(StepRun, RunbookRun.alert_id, Alert.team_id, Alert.occurrences, Alert.last_seen_at, RunbookRun.event)
            .join(RunbookRun, RunbookRun.id == StepRun.run_id)
            .join(Alert, Alert.id == RunbookRun.alert_id)
            .where(
                StepRun.run_at.is_not(None),
                StepRun.run_at <= now,
                or_(StepRun.lease_until.is_(None), StepRun.lease_until <= now),
                Alert.status != AlertStatus.RESOLVED,
            )
            .order_by(StepRun.run_at)
            .limit(limit)
            .with_for_update(of=StepRun, skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).all()
    if not rows:
        return []
    failures: dict[uuid.UUID, dict[int, int]] = {}
    unsettled: dict[uuid.UUID, set[int]] = {}
    for run_id, index, count, status, step in await session.execute(
        select(StepRun.run_id, StepRun.index, StepRun.failures, StepRun.status, StepRun.step).where(
            StepRun.run_id.in_({row[0].run_id for row in rows})
        )
    ):
        failures.setdefault(run_id, {})[index] = count
        if _can_still_fail(step, status):
            unsettled.setdefault(run_id, set()).add(index)
    jobs: list[StepJob] = []
    for step_run, alert_id, team_id, occurrences, last_seen_at, event in rows:
        due_at = step_run.run_at
        assert due_at is not None  # The claim selects only rows with `run_at` set.
        if step_run.lease_until is not None:
            step_run.errors += 1
        step_run.lease_until = now + lease
        jobs.append(
            StepJob(
                run_id=step_run.run_id,
                index=step_run.index,
                alert_id=alert_id,
                team_id=team_id,
                step=step_run.step,
                status=step_run.status,
                guard_answered=step_run.guard_answered,
                approved=step_run.approved,
                decided_by=step_run.decided_by,
                attempts=step_run.attempts,
                errors=step_run.errors,
                failures_by_index=failures[step_run.run_id],
                unsettled=frozenset(unsettled.get(step_run.run_id, ())),
                occurrences=occurrences,
                last_seen_at=last_seen_at,
                occurrences_at_run=step_run.occurrences_at_run,
                attempt_key=step_run.attempt_key,
                acted_at=step_run.acted_at,
                event=event,
                due_at=due_at,
                lease=now + lease,
                traceparent=step_run.traceparent,
            )
        )
    await session.flush()
    return jobs


async def _park_resolved(session: AsyncSession, now: datetime) -> None:
    """Take due steps of resolved alerts out of the claim (ADR-0095).

    `alerts.service.close_run` closes the run when the alert is resolved; this handles what it left. A `running` step
    whose lease ran out lost its replica after the resolve, so no outcome will arrive: a `wait` is skipped, an action
    fails with an unknown outcome, and the run finishes once every step is final (ADR-0104). Any other due step gets
    `run_at` null, which takes it out of the partial index instead of being scanned every poll.
    """
    resolved_runs = (
        select(RunbookRun.id)
        .join(Alert, Alert.id == RunbookRun.alert_id)
        .where(Alert.status == AlertStatus.RESOLVED)
        .scalar_subquery()
    )
    await session.execute(
        update(StepRun)
        .where(StepRun.run_at <= now, StepRun.status != StepStatus.RUNNING, StepRun.run_id.in_(resolved_runs))
        .values(run_at=None)
    )
    lost = (
        await session.execute(
            select(StepRun, RunbookRun.alert_id, Alert.team_id)
            .join(RunbookRun, RunbookRun.id == StepRun.run_id)
            .join(Alert, Alert.id == RunbookRun.alert_id)
            .where(
                StepRun.run_at <= now,
                StepRun.status == StepStatus.RUNNING,
                or_(StepRun.lease_until.is_(None), StepRun.lease_until <= now),
                Alert.status == AlertStatus.RESOLVED,
            )
            .with_for_update(of=(RunbookRun, StepRun), skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).all()
    for step_run, alert_id, team_id in lost:
        if isinstance(step_run.step, Wait):
            status, action, result = StepStatus.SKIPPED, AuditAction.STEP_SKIPPED, "The alert was resolved"
        else:
            status, action = StepStatus.FAILED, AuditAction.STEP_FAILED
            result = "Outcome unknown: the alert was resolved and the replica running the action was lost"
        step_run.status = status
        step_run.result = result
        step_run.run_at = None
        step_run.lease_until = None
        record(
            session,
            None,
            action,
            alert_id,
            team_id,
            {"run_id": str(step_run.run_id), "index": step_run.index, "status": status, "result": result},
        )
        _log.warning("executor.step_lost", run_id=str(step_run.run_id), index=step_run.index, status=status.value)
        await session.flush()
        statuses = (await session.scalars(select(StepRun.status).where(StepRun.run_id == step_run.run_id))).all()
        if all(is_final(s) for s in statuses):
            await finish_run(session, RunContext(step_run.run_id, alert_id, team_id, None), len(statuses), now)


@dataclass(frozen=True)
class Started:
    """A step run marked `running`, and the idempotency key its action must send."""

    job: StepJob
    key: uuid.UUID


async def start_step(session: AsyncSession, job: StepJob, now: datetime) -> Started | None:
    """Mark the step `running` with an idempotency key before its action runs, and audit `step.started` (ADR-0103).

    A step claimed while `running` lost the replica that ran its action: it keeps its key and `acted_at`, so the
    integration sees the same key again, and is not audited again. Writes only while the row holds the claim's lease
    and state; returns None, writing nothing, when it does not (the step is checked again by its next claim). The
    caller commits before acting.
    """
    resuming = job.status is StepStatus.RUNNING and job.attempt_key is not None
    key = job.attempt_key if resuming and job.attempt_key is not None else uuid.uuid7()
    acted_at = job.acted_at if resuming and job.acted_at is not None else now
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
        .values(status=StepStatus.RUNNING, attempt_key=key, acted_at=acted_at)
        .returning(StepRun.index)
    )
    if written is None:
        _log.warning("executor.step_start_stale", run_id=str(job.run_id), index=job.index)
        return None
    if not resuming:
        record(
            session,
            None,
            AuditAction.STEP_STARTED,
            job.alert_id,
            job.team_id,
            {
                "run_id": str(job.run_id),
                "index": job.index,
                "status": StepStatus.RUNNING,
                "result": None,
                "attempt_key": str(key),
            },
        )
    return Started(dataclasses.replace(job, status=StepStatus.RUNNING, attempt_key=key, acted_at=acted_at), key)
