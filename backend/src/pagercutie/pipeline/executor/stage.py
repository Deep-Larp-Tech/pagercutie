"""Entrypoints of the runbook executor, called by the orchestrator (`start_run`) and its loop (`worker.py`)."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, RunbookRun, StepRun
from pagercutie.alerts.schemas import StepDecisionKind, StepStatus
from pagercutie.audit.service import record_entry
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.errors import NotImplementedYet
from pagercutie.pipeline.messages import Opened
from pagercutie.rules import evaluator
from pagercutie.rules.evaluator import EventView
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.steps import Step

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


@dataclass(frozen=True)
class StepSucceeded:
    # Shown on the alert, e.g. "HTTP 200 in 35 ms".
    result: str


@dataclass(frozen=True)
class StepFailed:
    error: str


@dataclass(frozen=True)
class AwaitingApproval:
    """The action needs a lead's approval before it runs (RUN-4)."""


@dataclass(frozen=True)
class AwaitingAnswer:
    """An unparsed `if` guard waits for a yes or no in the UI (SPEC §11.4)."""

    question: str


@dataclass(frozen=True)
class AwaitingManual:
    """A `manual` step waits to be ticked off."""


@dataclass(frozen=True)
class StepSkipped:
    """The step's structured guard is false."""


type StepOutcome = StepSucceeded | StepFailed | AwaitingApproval | AwaitingAnswer | AwaitingManual | StepSkipped


async def start_run(session: AsyncSession, opened: Opened) -> uuid.UUID | None:
    """Create the runbook run and its step runs for a new alert and return the run's ID (SPEC §11.3).

    Returns None, writing nothing, when no runbook applies: the rule has none, the runbook no longer exists, or it
    has no steps. Idempotent on the alert (ADR-0008): when the alert already has a run, returns its ID without
    inserting steps, auditing or notifying again. Runs in the caller's transaction.
    """
    alert_id = opened.alert_id
    runbook = await _pick_runbook(session, opened)
    if runbook is None or not runbook.steps:
        return None
    event = opened.match.event
    run_id = await session.scalar(
        insert(RunbookRun)
        .values(
            id=uuid.uuid7(),
            alert_id=alert_id,
            runbook_id=runbook.id,
            event=evaluator.event_view(
                source=event.source, schema_id=event.schema_id, severity=event.severity, payload=event.payload
            ),
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


async def _pick_runbook(session: AsyncSession, opened: Opened) -> Runbook | None:
    """The runbook for the alert: the rule's link. Matching runbooks by `attach` extends this (RUN-1)."""
    runbook_id = opened.match.rule.runbook_id
    if runbook_id is None:
        return None
    runbook = await session.get(Runbook, runbook_id)
    if runbook is None:
        # The rule is a cached snapshot, so it can still name a runbook that was unlinked or deleted since.
        _log.warning("executor.runbook_missing", alert_id=str(opened.alert_id), runbook_id=str(runbook_id))
    return runbook


async def claim_due_steps(session: AsyncSession, limit: int, now: datetime) -> list[StepJob]:
    """Claim up to `limit` step runs whose `run_at` has passed, with `FOR UPDATE SKIP LOCKED`."""
    raise NotImplementedYet("Step claiming")


async def run_step(job: StepJob) -> StepOutcome:
    """Check the guard and approval, then run the step's action. Runs outside any transaction."""
    raise NotImplementedYet("Step execution")


async def complete_step(session: AsyncSession, job: StepJob, outcome: StepOutcome) -> None:
    """Store the outcome, audit it (RUN-5) and schedule the next step."""
    raise NotImplementedYet("Step completion")
