"""The `escalate` step (SPEC §11.4 step 5, RUN-3, ADR-0102)."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.pipeline.test_executor_loop import CONFIG, NOW, audit, claim, make_run, rows, set_step
from tests.integration.pipeline.test_routing import add_members, make_team, make_user, preferences

from pagercutie.alerts.models import Alert, Delivery
from pagercutie.alerts.schemas import DeliveryStatus, StepStatus
from pagercutie.audit.schemas import AuditAction
from pagercutie.core.enums import Channel, Severity
from pagercutie.pipeline.executor.outcomes import EscalationDue
from pagercutie.pipeline.executor.perform import Settle
from pagercutie.pipeline.executor.stage import complete_step, plan_step
from pagercutie.runbooks.steps import Escalate, Step
from pagercutie.teams.models import Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User

pytestmark = pytest.mark.anyio


@pytest.fixture
async def team(session: AsyncSession) -> Team:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    return team


@pytest.fixture
async def support(session: AsyncSession) -> tuple[Team, User, User, User]:
    """The escalation target with a lead, a member and a viewer; the team sends SMS for any severity."""
    support = await make_team(session, preferences(Channel.SMS, min_severity=Severity.DEBUG))
    lead = await make_user(session, "lead")
    member = await make_user(session, "member")
    viewer = await make_user(session, "viewer")
    await add_members(session, support, {lead: TeamRole.LEAD, member: TeamRole.MEMBER, viewer: TeamRole.VIEWER})
    return support, lead, member, viewer


async def escalate_once(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Approve the escalate step, claim it and complete it as the loop would."""
    await set_step(session, run_id, 0, status=StepStatus.PENDING, approved=True)
    job = await claim(session, run_id, 0)
    plan = plan_step(job, CONFIG.max_errors)
    assert isinstance(plan, Settle)
    assert isinstance(plan.outcome, EscalationDue)
    await complete_step(session, job, plan.outcome, NOW)


async def deliveries(session: AsyncSession, alert_id: uuid.UUID) -> set[tuple[uuid.UUID, Channel]]:
    rows = await session.execute(
        select(Delivery.user_id, Delivery.channel).where(
            Delivery.alert_id == alert_id, Delivery.status == DeliveryStatus.PENDING
        )
    )
    return {(user_id, channel) for user_id, channel in rows}


async def test_an_approved_escalation_adds_the_team_and_notifies_its_leads_and_members(
    session: AsyncSession, team: Team, support: tuple[Team, User, User, User]
) -> None:
    target, lead, member, _ = support
    steps: list[Step] = [Escalate(action="escalate", team=target.slug)]
    run_id, alert_id, _ = await make_run(session, team, steps)

    await escalate_once(session, run_id)

    (step,) = await rows(session, run_id)
    assert (step.status, step.result) == (StepStatus.SUCCEEDED, "Escalated to team Settlements")
    alert = await session.get_one(Alert, alert_id, populate_existing=True)
    assert alert.escalated_team_ids == [target.id]
    assert await deliveries(session, alert_id) == {
        (lead.id, Channel.SMS),
        (lead.id, Channel.UI),
        (member.id, Channel.SMS),
        (member.id, Channel.UI),
    }
    entries = await audit(session, run_id)
    assert [action for action, _ in entries] == [
        AuditAction.STEP_SUCCEEDED,
        AuditAction.ALERT_ESCALATED,
        AuditAction.RUNBOOK_RUN_FINISHED,
    ]
    assert entries[1][1] == {"index": 0, "escalated_team_id": str(target.id), "approved_by": None, "deliveries": 4}


async def test_a_repeated_escalation_creates_the_deliveries_and_adds_the_team_once(
    session: AsyncSession, team: Team, support: tuple[Team, User, User, User]
) -> None:
    target, *_ = support
    run_id, alert_id, _ = await make_run(session, team, [Escalate(action="escalate", team=target.slug)])

    await escalate_once(session, run_id)
    first = await deliveries(session, alert_id)
    await escalate_once(session, run_id)

    assert len(first) == 4
    count = await session.scalar(select(func.count()).select_from(Delivery).where(Delivery.alert_id == alert_id))
    assert count == 4
    alert = await session.get_one(Alert, alert_id, populate_existing=True)
    assert alert.escalated_team_ids == [target.id]
    escalations = [action for action, _ in await audit(session, run_id) if action is AuditAction.ALERT_ESCALATED]
    assert escalations == [AuditAction.ALERT_ESCALATED]


async def test_an_escalation_to_a_missing_team_fails_the_step(session: AsyncSession, team: Team) -> None:
    run_id, alert_id, _ = await make_run(session, team, [Escalate(action="escalate", team="nobody")])

    await escalate_once(session, run_id)

    (step,) = await rows(session, run_id)
    assert (step.status, step.failures, step.result) == (StepStatus.FAILED, 1, "No team has the slug 'nobody'")
    assert (await session.get_one(Alert, alert_id, populate_existing=True)).escalated_team_ids == []
    assert await deliveries(session, alert_id) == set()


async def test_a_stale_escalation_writes_nothing(
    session: AsyncSession, team: Team, support: tuple[Team, User, User, User]
) -> None:
    target, *_ = support
    run_id, alert_id, _ = await make_run(session, team, [Escalate(action="escalate", team=target.slug)])
    await set_step(session, run_id, 0, approved=True)
    job = await claim(session, run_id, 0)
    await set_step(session, run_id, 0, lease_until=None, run_at=None)

    await complete_step(session, job, EscalationDue(target.slug), NOW)

    assert (await session.get_one(Alert, alert_id, populate_existing=True)).escalated_team_ids == []
    assert await deliveries(session, alert_id) == set()
    assert await audit(session, run_id) == []
