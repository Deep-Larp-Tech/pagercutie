"""Alerts, their deliveries, runbook runs and the user actions on them (DOMAIN.md §6).

Permissions follow DOMAIN.md §4: any role in the alert's team or in a team it was escalated to reads the alert and
its deliveries; the owner of the rule reads a personal alert; admins read and do everything. An alert the actor
cannot see answers 404, so non-members cannot probe which alerts exist. `member` or `lead` of one of those teams, or
the owner of a personal alert, acknowledges and resolves it; a viewer gets 403. Every action locks the alert row,
writes an audit entry and issues `NOTIFY alert_changed` with an `AlertChanged` payload in the request's transaction
(SPEC §5.3, §12.1). The live feed (`GET /alerts/stream`) sends the same visible alerts, re-checking the actor per batch.

Runbook runs are read by anyone who sees the alert. A member or lead answers a guard question or ticks a manual step;
only a lead approves or rejects a risky step (RUN-4, ADR-0025). Every step decision locks the step row and writes an
audit entry.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import assert_never

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import ColumnElement, exists, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pagercutie.alerts.models import Alert, Delivery, RunbookRun, StepRun
from pagercutie.alerts.schemas import (
    AlertEvent,
    AlertEventType,
    AlertRead,
    AlertStatus,
    DeliveryRead,
    DeliveryStatus,
    Resolution,
    ResolveRequest,
    RunbookRunRead,
    StepDecision,
    StepDecisionKind,
    StepStatus,
)
from pagercutie.audit import service as audit
from pagercutie.audit.schemas import AuditAction
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.enums import Channel, Severity
from pagercutie.core.errors import Conflict, Forbidden, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.rules.models import Rule
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.schemas import GlobalRole

_ALERT = "Alert"
_RUN = "Runbook run of alert"
RESPONDERS = frozenset({TeamRole.MEMBER, TeamRole.LEAD})
_LEADS = frozenset({TeamRole.LEAD})
_FINAL_STEP_STATUSES = frozenset({StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED})


class AlertChanged(BaseModel):
    """Payload of `NOTIFY alert_changed`: which alert changed and how; about 80 bytes, under Postgres' 8000."""

    model_config = ConfigDict(frozen=True)

    type: AlertEventType
    alert_id: uuid.UUID


class FeedReloadNeeded(Exception):
    """A notification without a readable payload: the live feed cannot tell what changed, so the client reloads."""


# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_alerts(
    session: AsyncSession,
    actor: CurrentUser,
    pagination: Pagination,
    team_id: uuid.UUID | None,
    statuses: list[AlertStatus] | None,
    severities: list[Severity] | None,
) -> list[AlertRead]:
    """Visible alerts, most recently seen first. `team_id` is the team feed: owned by or escalated to the team."""
    query = select(Alert).where(visible_alerts_clause(actor))
    if team_id is not None:
        query = query.where(team_feed_clause(team_id))
    if statuses:
        query = query.where(Alert.status.in_(statuses))
    if severities:
        query = query.where(Alert.severity.in_(severities))
    query = query.order_by(Alert.last_seen_at.desc(), Alert.id.desc())
    query = query.limit(pagination.limit).offset(pagination.offset)
    return [AlertRead.model_validate(alert) for alert in await session.scalars(query)]


async def get_alert(session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID) -> AlertRead:
    return AlertRead.model_validate(await get_visible_alert(session, actor, alert_id))


async def acknowledge_alert(session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID) -> AlertRead:
    """`member`/`lead` of the alert's or an escalated team, or a personal alert's owner. 409 unless open."""
    alert = await get_visible_alert(session, actor, alert_id, for_update=True)
    await require_alert_role(session, actor, alert, RESPONDERS)
    if alert.status is not AlertStatus.OPEN:
        raise Conflict(f"Alert {alert_id} is {alert.status}; only open alerts can be acknowledged")
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = actor.id
    alert.acknowledged_at = datetime.now(UTC)
    audit.record(session, actor.id, AuditAction.ALERT_ACKNOWLEDGED, alert.id, alert.team_id, {})
    await session.flush()
    await notify_alert_changed(session, alert.id, "alert.updated")
    return AlertRead.model_validate(alert)


async def resolve_alert(
    session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID, data: ResolveRequest
) -> AlertRead:
    """Same roles as acknowledge; from `open` or `acknowledged`. 409 when already resolved. Closes the alert's runbook
    run."""
    alert = await get_visible_alert(session, actor, alert_id, for_update=True)
    await require_alert_role(session, actor, alert, RESPONDERS)
    if alert.status is AlertStatus.RESOLVED:
        raise Conflict(f"Alert {alert_id} is already resolved")
    alert.status = AlertStatus.RESOLVED
    alert.resolution = Resolution.MANUAL
    alert.resolved_by = actor.id
    alert.resolved_at = datetime.now(UTC)
    audit.record(session, actor.id, AuditAction.ALERT_RESOLVED, alert.id, alert.team_id, {"note": data.note})
    await close_run(session, actor.id, alert)
    await session.flush()
    await notify_alert_changed(session, alert.id, "alert.updated")
    return AlertRead.model_validate(alert)


async def feed_events(
    session: AsyncSession, actor: CurrentUser, payloads: Sequence[str], team_id: uuid.UUID | None
) -> list[AlertEvent]:
    """One event per changed alert the actor sees (in `team_id`'s feed when given), in first-notified order.

    `alert.created` wins when one batch holds both types for an alert. `FeedReloadNeeded` for a payload that is not
    an `AlertChanged`."""
    changes: dict[uuid.UUID, AlertEventType] = {}
    for payload in payloads:
        try:
            change = AlertChanged.model_validate_json(payload)
        except ValidationError as e:
            raise FeedReloadNeeded from e
        if changes.get(change.alert_id) != "alert.created":
            changes[change.alert_id] = change.type
    query = select(Alert).where(Alert.id.in_(changes), visible_alerts_clause(actor))
    if team_id is not None:
        query = query.where(team_feed_clause(team_id))
    alerts = {alert.id: alert for alert in await session.scalars(query)}
    return [
        AlertEvent(type=change, alert=AlertRead.model_validate(alerts[alert_id]))
        for alert_id, change in changes.items()
        if alert_id in alerts
    ]


async def list_alert_deliveries(session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID) -> list[DeliveryRead]:
    """Every delivery of a visible alert, newest first."""
    await get_visible_alert(session, actor, alert_id)
    deliveries = await session.scalars(
        select(Delivery).where(Delivery.alert_id == alert_id).order_by(Delivery.created_at.desc(), Delivery.id.desc())
    )
    return [DeliveryRead.model_validate(d) for d in deliveries]


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
    """Anyone who sees the alert. None when the alert's rule has no runbook, so no run was started."""
    alert = await get_visible_alert(session, actor, alert_id)
    run = await _load_run(session, alert.id)
    return None if run is None else RunbookRunRead.model_validate(run)


async def decide_step(
    session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID, index: int, data: StepDecision
) -> RunbookRunRead:
    """Apply a person's decision to a waiting step (DOMAIN §6). 409 when the step's status does not fit."""
    alert = await get_visible_alert(session, actor, alert_id)
    run = await _load_run(session, alert.id)
    if run is None:
        raise NotFound(_RUN, alert.id)
    rule = _decision_rule(data.decision)
    await require_alert_role(session, actor, alert, rule.roles)
    # Serialises two people deciding at once: the second sees the new status (409). populate_existing refreshes the
    # instance `run.steps` already holds.
    step = await session.scalar(
        select(StepRun)
        .where(StepRun.run_id == run.id, StepRun.index == index)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if step is None:
        raise NotFound(f"Step {index} of runbook run", run.id)
    if step.status is not rule.awaits:
        raise Conflict(f"Step {index} is {step.status}; '{data.decision}' needs {rule.awaits}")

    previous = step.status
    now = datetime.now(UTC)
    step.decided_by = actor.id
    step.decided_at = now
    match data.decision:
        case StepDecisionKind.APPROVE:
            step.approved = True
            _rerun(step, now)
        case StepDecisionKind.YES:
            step.guard_answered = True
            _rerun(step, now)
        case StepDecisionKind.REJECT | StepDecisionKind.NO:
            step.status = StepStatus.SKIPPED
            step.result = data.note
            schedule_next_step(run, index, now)
        case StepDecisionKind.DONE:
            step.status = StepStatus.SUCCEEDED
            step.result = data.note
            schedule_next_step(run, index, now)
        case _:
            assert_never(data.decision)
    audit.record(
        session,
        actor.id,
        rule.audit_action,
        alert.id,
        alert.team_id,
        {
            "run_id": str(run.id),
            "index": index,
            "decision": data.decision,
            "from": previous,
            "to": step.status,
            "note": data.note,
        },
    )
    await session.flush()
    if any(s.run_at == now for s in run.steps):
        # Wakes the executor so it does not wait for its poll.
        await notify(session, NotifyChannel.STEPS_PENDING)
    await notify_alert_changed(session, alert.id, "alert.updated")
    return RunbookRunRead.model_validate(run)


async def close_run(session: AsyncSession, actor_user_id: uuid.UUID | None, alert: Alert) -> None:
    """Skip the unfinished steps of `alert`'s runbook run and stop a watching retry, so nothing runs after the alert
    is resolved (RUN-5, ADR-0095). The caller holds the alert's row lock.

    Each skipped step is audited with the actor, and `runbook_run.finished` once when a step was skipped. An outcome
    the executor writes later is dropped: its update is conditional on the status and lease this changes.
    """
    run = await session.scalar(select(RunbookRun).where(RunbookRun.alert_id == alert.id))
    if run is None:
        return
    steps = (
        await session.scalars(
            select(StepRun)
            .where(StepRun.run_id == run.id)
            .order_by(StepRun.index)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    skipped = 0
    for step in steps:
        step.run_at = None
        if step.status in _FINAL_STEP_STATUSES:
            continue
        previous = step.status
        step.status = StepStatus.SKIPPED
        skipped += 1
        audit.record(
            session,
            actor_user_id,
            AuditAction.STEP_SKIPPED,
            alert.id,
            alert.team_id,
            {"run_id": str(run.id), "index": step.index, "from": previous, "to": step.status, "reason": "resolved"},
        )
    if skipped:
        audit.record(
            session,
            actor_user_id,
            AuditAction.RUNBOOK_RUN_FINISHED,
            alert.id,
            alert.team_id,
            {"run_id": str(run.id), "steps": len(steps)},
        )


def schedule_next_step(run: RunbookRun, index: int, now: datetime) -> None:
    """Make the step after `index` due now; nothing after the last step. Shared with the executor's `complete_step`.

    `run.steps` must be loaded.
    """
    following = next((s for s in run.steps if s.index == index + 1), None)
    if following is not None and following.status is StepStatus.PENDING:
        following.run_at = now


# --- Rules (shared with runbook step decisions and the live feed) ----------------------------------------------


def visible_alerts_clause(actor: CurrentUser) -> ColumnElement[bool]:
    """Predicate on `Alert` for the alerts `actor` may see; correlates with `rules` for personal alerts."""
    if actor.role is GlobalRole.ADMIN:
        return true()
    team_ids = list(actor.team_roles)
    own_rule = exists().where(Rule.id == Alert.rule_id, Rule.user_id == actor.id)
    if not team_ids:
        return own_rule
    return or_(Alert.team_id.in_(team_ids), Alert.escalated_team_ids.overlap(team_ids), own_rule)


def team_feed_clause(team_id: uuid.UUID) -> ColumnElement[bool]:
    """Predicate on `Alert` for a team's feed: owned by the team or escalated to it."""
    return or_(Alert.team_id == team_id, Alert.escalated_team_ids.contains([team_id]))


async def notify_alert_changed(session: AsyncSession, alert_id: uuid.UUID, change: AlertEventType) -> None:
    """`NOTIFY alert_changed` with an `AlertChanged` payload, sent on commit; every alert write calls it (SPEC §5.3)."""
    await notify(session, NotifyChannel.ALERT_CHANGED, AlertChanged(type=change, alert_id=alert_id).model_dump_json())


async def get_visible_alert(
    session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID, *, for_update: bool = False
) -> Alert:
    """The alert, or `NotFound` when it is missing or not visible. `for_update` locks the row until commit."""
    query = select(Alert).where(Alert.id == alert_id, visible_alerts_clause(actor))
    if for_update:
        # populate_existing: an instance already in the session would otherwise keep its pre-lock values.
        query = query.with_for_update(of=Alert).execution_options(populate_existing=True)
    alert = await session.scalar(query)
    if alert is None:
        raise NotFound(_ALERT, alert_id)
    return alert


async def require_alert_role(
    session: AsyncSession, actor: CurrentUser, alert: Alert, roles: frozenset[TeamRole]
) -> None:
    """`Forbidden` unless `actor` has one of `roles` in the alert's team or an escalated team, owns the rule of a
    personal alert, or is an admin."""
    if actor.role is GlobalRole.ADMIN:
        return
    team_ids = [alert.team_id, *alert.escalated_team_ids] if alert.team_id is not None else alert.escalated_team_ids
    if any(actor.team_roles.get(team_id) in roles for team_id in team_ids):
        return
    # A personal rule has no team roles: its owner is the only responder (ADR-0026).
    if alert.team_id is None and await session.scalar(
        select(exists().where(Rule.id == alert.rule_id, Rule.user_id == actor.id))
    ):
        return
    raise Forbidden(f"Needs role {' or '.join(sorted(roles))} in the alert's team or an escalated team")


@dataclass(frozen=True)
class _DecisionRule:
    awaits: StepStatus
    roles: frozenset[TeamRole]
    audit_action: AuditAction


def _decision_rule(decision: StepDecisionKind) -> _DecisionRule:
    """Which status a decision applies to, who may make it and how it is audited (DOMAIN §4, §6)."""
    match decision:
        case StepDecisionKind.APPROVE:
            return _DecisionRule(
                awaits=StepStatus.AWAITING_APPROVAL, roles=_LEADS, audit_action=AuditAction.STEP_APPROVED
            )
        case StepDecisionKind.REJECT:
            return _DecisionRule(
                awaits=StepStatus.AWAITING_APPROVAL, roles=_LEADS, audit_action=AuditAction.STEP_REJECTED
            )
        case StepDecisionKind.YES:
            return _DecisionRule(
                awaits=StepStatus.AWAITING_ANSWER, roles=RESPONDERS, audit_action=AuditAction.STEP_ANSWERED
            )
        case StepDecisionKind.NO:
            return _DecisionRule(
                awaits=StepStatus.AWAITING_ANSWER, roles=RESPONDERS, audit_action=AuditAction.STEP_ANSWERED
            )
        case StepDecisionKind.DONE:
            return _DecisionRule(
                awaits=StepStatus.AWAITING_MANUAL, roles=RESPONDERS, audit_action=AuditAction.STEP_DONE
            )
        case _:
            assert_never(decision)


def _rerun(step: StepRun, now: datetime) -> None:
    # The executor re-checks the remaining gates with the cleared flags.
    step.status = StepStatus.PENDING
    step.run_at = now


async def _load_run(session: AsyncSession, alert_id: uuid.UUID) -> RunbookRun | None:
    return await session.scalar(
        select(RunbookRun).where(RunbookRun.alert_id == alert_id).options(selectinload(RunbookRun.steps))
    )


async def list_deliveries(
    session: AsyncSession,
    actor: CurrentUser,
    pagination: Pagination,
    channels: list[Channel] | None,
    statuses: list[DeliveryStatus] | None,
) -> list[DeliveryRead]:
    """Deliveries of the alerts the actor can see, newest first, optionally only these channels and statuses."""
    query = select(Delivery).join(Alert, Alert.id == Delivery.alert_id).where(visible_alerts_clause(actor))
    if channels:
        query = query.where(Delivery.channel.in_(channels))
    if statuses:
        query = query.where(Delivery.status.in_(statuses))
    query = query.order_by(Delivery.created_at.desc(), Delivery.id.desc())
    query = query.limit(pagination.limit).offset(pagination.offset)
    return [DeliveryRead.model_validate(d) for d in await session.scalars(query)]
