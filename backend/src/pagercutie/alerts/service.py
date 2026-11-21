import uuid
from datetime import UTC, datetime
from typing import assert_never

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pagercutie.alerts.models import Alert, Delivery, RunbookRun, StepRun
from pagercutie.alerts.schemas import (
    AlertStatus,
    DeliveryRead,
    RunbookRunRead,
    StepDecision,
    StepDecisionKind,
    expected_status,
)
from pagercutie.audit.schemas import AuditAction
from pagercutie.audit.service import record
from pagercutie.auth.service import CurrentUser
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.enums import Channel
from pagercutie.core.errors import Conflict, Forbidden, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.rules.models import Rule
from pagercutie.teams.schemas import TeamRole


async def list_user_deliveries(
    session: AsyncSession, user_id: uuid.UUID, pagination: Pagination, channels: list[Channel] | None
) -> list[DeliveryRead]:
    """The user's deliveries, newest first, optionally only on these channels."""
    query = select(Delivery).where(Delivery.user_id == user_id)
    if channels:
        query = query.where(Delivery.channel.in_(channels))
    query = query.order_by(Delivery.created_at.desc(), Delivery.id.desc())
    query = query.limit(pagination.limit).offset(pagination.offset)
    return [DeliveryRead.model_validate(d) for d in await session.scalars(query)]


async def get_runbook_run(session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID) -> RunbookRunRead | None:
    """The alert's runbook run with its steps in index order; None when the alert has no run.

    Raises `NotFound` for a missing alert and for one the actor may not see (DOMAIN §4).
    """
    await _visible_alert(session, actor, alert_id)
    run = await _load_run(session, alert_id)
    return None if run is None else RunbookRunRead.model_validate(run)


async def decide_step(
    session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID, index: int, data: StepDecision
) -> RunbookRunRead:
    """Record a human decision on a step run and wake the executor, which applies it (SPEC §11.3, DOMAIN §6).

    Only `decision`, `decided_by`, `decided_at` and `run_at` change: the executor owns every status transition.
    Raises `NotFound` (no visible alert, run or step), `Forbidden` (role), `Conflict` (resolved alert, step not
    waiting for this decision, or an earlier decision the executor has not applied yet).
    """
    alert, owner_id = await _visible_alert(session, actor, alert_id)
    run = await _load_run(session, alert_id)
    if run is None:
        raise NotFound("Runbook run of alert", alert_id)
    # Refresh the step already loaded with the run, under a row lock, so a concurrent decision or claim is seen.
    step = await session.scalar(
        select(StepRun)
        .where(StepRun.run_id == run.id, StepRun.index == index)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if step is None:
        raise NotFound(f"Step {index} of runbook run", run.id)
    if not _can_decide(actor, alert, owner_id, data.decision):
        raise Forbidden(f"Your role may not record the decision {data.decision}")
    if alert.status is AlertStatus.RESOLVED:
        raise Conflict("The alert is resolved")
    if step.status is not expected_status(data.decision):
        raise Conflict(f"Step {index} is {step.status}, so it cannot take the decision {data.decision}")
    if step.decision is not None and expected_status(step.decision) is step.status:
        raise Conflict(f"Step {index} already has the decision {step.decision}, which is not applied yet")
    now = datetime.now(UTC)
    step.decision = data.decision
    step.decided_by = actor.id
    step.decided_at = now
    step.run_at = now
    audit_data: dict[str, JsonValue] = {
        "run_id": str(run.id),
        "index": index,
        "decision": data.decision.value,
        "note": data.note,
    }
    match data.decision:
        case StepDecisionKind.APPROVE:
            action = AuditAction.STEP_APPROVED
        case StepDecisionKind.REJECT:
            action = AuditAction.STEP_REJECTED
        case StepDecisionKind.YES | StepDecisionKind.NO:
            action = AuditAction.STEP_ANSWERED
            audit_data["answer"] = data.decision.value
        case StepDecisionKind.DONE:
            action = AuditAction.STEP_DONE
        case _:
            assert_never(data.decision)
    record(session, actor.id, action, alert.id, alert.team_id, audit_data)
    await notify(session, NotifyChannel.STEPS_PENDING)
    return RunbookRunRead.model_validate(run)


async def _load_run(session: AsyncSession, alert_id: uuid.UUID) -> RunbookRun | None:
    return await session.scalar(
        select(RunbookRun).where(RunbookRun.alert_id == alert_id).options(selectinload(RunbookRun.steps))
    )


async def _visible_alert(
    session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID
) -> tuple[Alert, uuid.UUID | None]:
    """The alert and the user owning its rule (a personal rule), or `NotFound` when the actor may not see it."""
    row = (
        await session.execute(
            select(Alert, Rule.user_id).join(Rule, Rule.id == Alert.rule_id).where(Alert.id == alert_id)
        )
    ).one_or_none()
    if row is None:
        raise NotFound("Alert", alert_id)
    alert, owner_id = row
    if not _can_see(actor, alert, owner_id):
        raise NotFound("Alert", alert_id)
    return alert, owner_id


def _alert_team_roles(actor: CurrentUser, alert: Alert) -> set[TeamRole]:
    """The actor's roles in the alert's team and in the teams it was escalated to."""
    team_ids = set(alert.escalated_team_ids)
    if alert.team_id is not None:
        team_ids.add(alert.team_id)
    return {role for team_id, role in actor.team_roles.items() if team_id in team_ids}


def _can_see(actor: CurrentUser, alert: Alert, owner_id: uuid.UUID | None) -> bool:
    """Admin, the owner of a personal rule, or any role in the alert's team or an escalated team (DOMAIN §4)."""
    return actor.is_admin or owner_id == actor.id or bool(_alert_team_roles(actor, alert))


def _can_decide(actor: CurrentUser, alert: Alert, owner_id: uuid.UUID | None, decision: StepDecisionKind) -> bool:
    """`approve`/`reject` need a lead, the others a member or lead; admin and a personal rule's owner may do all."""
    if actor.is_admin or owner_id == actor.id:
        return True
    roles = _alert_team_roles(actor, alert)
    match decision:
        case StepDecisionKind.APPROVE | StepDecisionKind.REJECT:
            return TeamRole.LEAD in roles
        case StepDecisionKind.YES | StepDecisionKind.NO | StepDecisionKind.DONE:
            return not roles.isdisjoint({TeamRole.MEMBER, TeamRole.LEAD})
        case _:
            assert_never(decision)
