"""How a runbook run moves on: which step statuses are final and which step runs next (SPEC §11.3, ADR-0105).

Shared by the decision endpoint (`alerts.service`) and the executor stage, which may import entity packages; the
pipeline may not be imported from here (SPEC §5.5).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import RunbookRun, StepRun
from pagercutie.alerts.schemas import StepStatus
from pagercutie.audit import service as audit
from pagercutie.audit.schemas import AuditAction
from pagercutie.core.db import NotifyChannel, notify


def is_final(status: StepStatus) -> bool:
    """Whether a step run in `status` is done: `succeeded`, `failed` or `skipped`."""
    match status:
        case StepStatus.SUCCEEDED | StepStatus.FAILED | StepStatus.SKIPPED:
            return True
        case (
            StepStatus.PENDING
            | StepStatus.AWAITING_APPROVAL
            | StepStatus.AWAITING_ANSWER
            | StepStatus.AWAITING_MANUAL
            | StepStatus.RUNNING
        ):
            return False
        case _:
            assert_never(status)


FINAL_STEP_STATUSES = frozenset(status for status in StepStatus if is_final(status))
"""`is_final` as a set, for SQL `IN` clauses."""


@dataclass(frozen=True)
class RunContext:
    """The run a step belongs to and who is acting, for scheduling and audit entries."""

    run_id: uuid.UUID
    alert_id: uuid.UUID
    # The alert's team; null for a personal rule's alert.
    team_id: uuid.UUID | None
    # The person whose decision moved the run on; null for the executor.
    actor_user_id: uuid.UUID | None


@dataclass(frozen=True)
class Advanced:
    """What `advance_run` did."""

    # The index of the step made due now; null when none was.
    scheduled: int | None
    # The run finished with this call (`runbook_run.finished` was audited).
    finished: bool


async def lock_run(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Lock the run row until commit. Every writer of a run's steps takes it before any step row (run, then steps), so
    two writers never deadlock and the one that finishes the run sees the other's committed steps."""
    await session.execute(select(RunbookRun.id).where(RunbookRun.id == run_id).with_for_update())


async def advance_run(session: AsyncSession, run: RunContext, after_index: int, now: datetime) -> Advanced:
    """After step `after_index` finished: make the next `pending` step due, or finish the run when every step is final.

    The next step is the first `pending` step with a higher index; its `run_at` becomes `now`. A step that holds a live
    lease keeps it: `run_at` only says when to look at the step, the lease alone keeps a second replica from claiming
    it, and an outcome that would park it (`GuardPending`) keeps this newer `run_at` (ADR-0105). Finishing sets
    `finished_at` once and audits `runbook_run.finished` with `run.actor_user_id`. The caller holds `lock_run` and
    commits.
    """
    steps = (
        await session.execute(
            select(StepRun.index, StepRun.status).where(StepRun.run_id == run.run_id).order_by(StepRun.index)
        )
    ).all()
    following = next((index for index, status in steps if index > after_index and status is StepStatus.PENDING), None)
    if following is not None:
        await session.execute(
            update(StepRun).where(StepRun.run_id == run.run_id, StepRun.index == following).values(run_at=now)
        )
        await notify(session, NotifyChannel.STEPS_PENDING)
        return Advanced(scheduled=following, finished=False)
    if not all(is_final(status) for _, status in steps):
        return Advanced(scheduled=None, finished=False)
    return Advanced(scheduled=None, finished=await finish_run(session, run, len(steps), now))


async def finish_run(session: AsyncSession, run: RunContext, steps: int, now: datetime) -> bool:
    """Set the run's `finished_at` and audit `runbook_run.finished`, unless it finished before; returns whether it did.

    The caller checked that every step is final and holds `lock_run`.
    """
    finished = await session.scalar(
        update(RunbookRun)
        .where(RunbookRun.id == run.run_id, RunbookRun.finished_at.is_(None))
        .values(finished_at=now)
        .returning(RunbookRun.id)
    )
    if finished is None:
        return False
    audit.record(
        session,
        run.actor_user_id,
        AuditAction.RUNBOOK_RUN_FINISHED,
        run.alert_id,
        run.team_id,
        {"run_id": str(run.run_id), "steps": steps},
    )
    return True
