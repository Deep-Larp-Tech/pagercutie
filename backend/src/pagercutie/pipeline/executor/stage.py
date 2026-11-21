"""Entrypoints of the runbook executor, called by the orchestrator (`start_run`) and its loop (`worker.py`)."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.schemas import StepDecisionKind, StepStatus
from pagercutie.core.errors import NotImplementedYet
from pagercutie.pipeline.messages import Opened
from pagercutie.rules.evaluator import EventView
from pagercutie.runbooks.steps import Step


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
    """Create the runbook run and its step runs for a new alert; None when the rule has no runbook (SPEC §11.3)."""
    raise NotImplementedYet("Runbook run creation")


async def claim_due_steps(session: AsyncSession, limit: int, now: datetime) -> list[StepJob]:
    """Claim up to `limit` step runs whose `run_at` has passed, with `FOR UPDATE SKIP LOCKED`."""
    raise NotImplementedYet("Step claiming")


async def run_step(job: StepJob) -> StepOutcome:
    """Check the guard and approval, then run the step's action. Runs outside any transaction."""
    raise NotImplementedYet("Step execution")


async def complete_step(session: AsyncSession, job: StepJob, outcome: StepOutcome) -> None:
    """Store the outcome, audit it (RUN-5) and schedule the next step."""
    raise NotImplementedYet("Step completion")
