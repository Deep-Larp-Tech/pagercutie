import uuid
from collections.abc import Sequence

import pytest
from httpx import AsyncClient
from pydantic import JsonValue, TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import AlertChanges
from tests.integration.pipeline.test_executor_loop import NOW, FakeHttp, make_run, rows, set_step
from tests.integration.pipeline.test_executor_start import STEPS, open_alert

from pagercutie.alerts.models import Alert, StepRun
from pagercutie.alerts.schemas import StepDecisionKind, StepStatus
from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction, AuditEntityType
from pagercutie.pipeline.executor import worker
from pagercutie.pipeline.executor.actions import Integrations, SimulatedOps
from pagercutie.pipeline.executor.outcomes import StepSucceeded
from pagercutie.pipeline.executor.stage import claim_due_steps, complete_step, start_run
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import HttpGet, Step
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

APPROVE = {"decision": "approve"}


async def make_user(
    session: AsyncSession, name: str, team: Team | None = None, role: TeamRole = TeamRole.MEMBER
) -> User:
    user = User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=GlobalRole.USER)
    session.add(user)
    await session.flush()
    if team is not None:
        session.add(Membership(team_id=team.id, user_id=user.id, role=role))
        await session.flush()
    return user


async def login(client: AsyncClient, user: User) -> None:
    response = await client.post("/auth/login", json={"email": user.email})
    assert response.status_code == 200


@pytest.fixture
async def payments(session: AsyncSession) -> Team:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    return team


@pytest.fixture
async def search(session: AsyncSession) -> Team:
    team = Team(slug="search", name="Search")
    session.add(team)
    await session.flush()
    return team


@pytest.fixture
async def lead(session: AsyncSession, payments: Team) -> User:
    return await make_user(session, "lead", payments, TeamRole.LEAD)


@pytest.fixture
async def member(session: AsyncSession, payments: Team) -> User:
    return await make_user(session, "member", payments)


@pytest.fixture
async def viewer(session: AsyncSession, payments: Team) -> User:
    return await make_user(session, "viewer", payments, TeamRole.VIEWER)


@pytest.fixture
async def outsider(session: AsyncSession, search: Team) -> User:
    return await make_user(session, "outsider", search, TeamRole.LEAD)


@pytest.fixture
async def admin(session: AsyncSession) -> User:
    user = User(email="admin@example.com", display_name="Admin", timezone="UTC", role=GlobalRole.ADMIN)
    session.add(user)
    await session.flush()
    return user


async def make_personal_run(session: AsyncSession, team: Team, owner: User) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns the run ID and alert ID of a run on an alert of `owner`'s personal rule."""
    runbook = Runbook(
        slug="personal", title="Retry", team_id=team.id, format=RunbookFormat.STRUCTURED, original="", steps=STEPS
    )
    session.add(runbook)
    await session.flush()
    opened = await open_alert(session, team, runbook.id, user=owner)
    run_id = await start_run(session, opened)
    assert run_id is not None
    return run_id, opened.alert_id


def run_url(alert_id: uuid.UUID) -> str:
    return f"/alerts/{alert_id}/runbook-run"


def decision_url(alert_id: uuid.UUID, index: int) -> str:
    return f"{run_url(alert_id)}/steps/{index}/decision"


DECISION_ACTIONS = [
    AuditAction.STEP_APPROVED,
    AuditAction.STEP_REJECTED,
    AuditAction.STEP_ANSWERED,
    AuditAction.STEP_DONE,
]


async def decisions(session: AsyncSession, alert_id: uuid.UUID) -> list[AuditEntry]:
    return list(
        await session.scalars(
            select(AuditEntry).where(AuditEntry.action.in_(DECISION_ACTIONS), AuditEntry.entity_id == alert_id)
        )
    )


async def waiting(session: AsyncSession, run_id: uuid.UUID, index: int, status: StepStatus, **values: object) -> None:
    """Puts step `index` into `status`, waiting for a person (no `run_at`)."""
    await set_step(session, run_id, index, status=status, run_at=None, **values)


# --- GET ---------------------------------------------------------------------------------------------------------


async def test_a_team_member_reads_the_run_with_steps_in_order(
    client: AsyncClient, session: AsyncSession, payments: Team, member: User, lead: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await set_step(session, run_id, 1, decided_by=lead.id)
    await login(client, member)

    response = await client.get(run_url(alert_id))

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["alert_id"]) == (str(run_id), str(alert_id))
    assert [step["index"] for step in body["steps"]] == [0, 1, 2]
    assert body["steps"][1]["decided_by"] == str(lead.id)
    assert body["steps"][0]["status"] == "pending"


async def test_a_user_of_another_team_gets_404(
    client: AsyncClient, session: AsyncSession, payments: Team, outsider: User
) -> None:
    _, alert_id, _ = await make_run(session, payments)
    await login(client, outsider)

    assert (await client.get(run_url(alert_id))).status_code == 404


async def test_a_member_of_an_escalated_team_reads_the_run(
    client: AsyncClient, session: AsyncSession, payments: Team, search: Team, outsider: User
) -> None:
    _, alert_id, _ = await make_run(session, payments)
    await session.execute(update(Alert).where(Alert.id == alert_id).values(escalated_team_ids=[search.id]))
    await login(client, outsider)

    assert (await client.get(run_url(alert_id))).status_code == 200


async def test_the_owner_of_a_personal_rule_reads_the_run(
    client: AsyncClient, session: AsyncSession, payments: Team, member: User
) -> None:
    owner = await make_user(session, "owner")
    _, alert_id = await make_personal_run(session, payments, owner)

    await login(client, member)
    assert (await client.get(run_url(alert_id))).status_code == 404
    await login(client, owner)
    assert (await client.get(run_url(alert_id))).status_code == 200


async def test_an_alert_without_a_run_answers_null(
    client: AsyncClient, session: AsyncSession, payments: Team, member: User
) -> None:
    opened = await open_alert(session, payments, None)
    await login(client, member)

    response = await client.get(run_url(opened.alert_id))

    assert response.status_code == 200
    assert response.json() is None


async def test_an_unknown_alert_gets_404(client: AsyncClient, member: User) -> None:
    await login(client, member)

    assert (await client.get(run_url(uuid.uuid4()))).status_code == 404


async def test_reading_the_run_needs_a_login(client: AsyncClient) -> None:
    assert (await client.get(run_url(uuid.uuid4()))).status_code == 401
    assert (await client.post(decision_url(uuid.uuid4(), 0), json=APPROVE)).status_code == 401


# --- POST decision -----------------------------------------------------------------------------------------------


async def test_a_lead_approves_and_the_step_is_due_again_with_the_gate_cleared(
    client: AsyncClient, session: AsyncSession, payments: Team, lead: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 0, StepStatus.AWAITING_APPROVAL)
    await login(client, lead)

    response = await client.post(decision_url(alert_id, 0), json={"decision": "approve", "note": "go ahead"})

    assert response.status_code == 200
    first = response.json()["steps"][0]
    assert (first["status"], first["decided_by"]) == ("pending", str(lead.id))
    step = (await rows(session, run_id))[0]
    assert (step.status, step.approved, step.guard_answered, step.decided_by) == (
        StepStatus.PENDING,
        True,
        False,
        lead.id,
    )
    assert step.decided_at is not None
    assert step.run_at == step.decided_at
    (entry,) = await decisions(session, alert_id)
    assert (entry.actor_user_id, entry.entity_type, entry.team_id) == (lead.id, AuditEntityType.ALERT, payments.id)
    assert entry.action is AuditAction.STEP_APPROVED
    assert entry.data == {
        "run_id": str(run_id),
        "index": 0,
        "decision": "approve",
        "from": "awaiting_approval",
        "to": "pending",
        "note": "go ahead",
    }


async def test_a_member_answers_yes_and_the_step_is_due_again_with_the_guard_cleared(
    client: AsyncClient, session: AsyncSession, payments: Team, member: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 2, StepStatus.AWAITING_ANSWER)
    await login(client, member)

    assert (await client.post(decision_url(alert_id, 2), json={"decision": "yes"})).status_code == 200

    step = (await rows(session, run_id))[2]
    assert (step.status, step.guard_answered, step.approved) == (StepStatus.PENDING, True, False)
    assert step.run_at is not None


@pytest.mark.parametrize(
    ("decision", "status", "index"),
    [("reject", StepStatus.AWAITING_APPROVAL, 0), ("no", StepStatus.AWAITING_ANSWER, 0)],
)
async def test_a_rejection_skips_the_step_and_makes_the_next_one_due(
    client: AsyncClient,
    session: AsyncSession,
    payments: Team,
    admin: User,
    decision: str,
    status: StepStatus,
    index: int,
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, index, status)
    await login(client, admin)

    response = await client.post(decision_url(alert_id, index), json={"decision": decision, "note": "not now"})

    assert response.status_code == 200
    first, second, _ = await rows(session, run_id)
    assert (first.status, first.result, first.approved, first.guard_answered) == (
        StepStatus.SKIPPED,
        "not now",
        False,
        False,
    )
    assert second.run_at == first.decided_at


async def test_done_marks_the_manual_step_succeeded_and_makes_the_next_one_due(
    client: AsyncClient, session: AsyncSession, payments: Team, member: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 1, StepStatus.AWAITING_MANUAL)
    await login(client, member)

    response = await client.post(decision_url(alert_id, 1), json={"decision": "done", "note": "checked"})

    assert response.status_code == 200
    _, second, third = await rows(session, run_id)
    assert (second.status, second.result) == (StepStatus.SUCCEEDED, "checked")
    assert third.run_at == second.decided_at


@pytest.mark.parametrize("decision", ["done", "no"])
async def test_a_decision_announces_the_alert(
    client: AsyncClient,
    session: AsyncSession,
    payments: Team,
    member: User,
    alert_changes: AlertChanges,
    decision: str,
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 1, StepStatus.AWAITING_MANUAL if decision == "done" else StepStatus.AWAITING_ANSWER)
    await login(client, member)
    alert_changes.clear()

    assert (await client.post(decision_url(alert_id, 1), json={"decision": decision})).status_code == 200

    assert alert_changes == [(alert_id, "alert.updated")]


async def test_a_decision_on_the_last_step_makes_no_step_due(
    client: AsyncClient, session: AsyncSession, payments: Team, member: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 2, StepStatus.AWAITING_ANSWER)
    await login(client, member)

    assert (await client.post(decision_url(alert_id, 2), json={"decision": "no"})).status_code == 200

    assert (await rows(session, run_id))[2].status is StepStatus.SKIPPED


async def test_the_executor_runs_an_approved_step(
    client: AsyncClient,
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    payments: Team,
    lead: User,
) -> None:
    steps: Sequence[Step] = [HttpGet(action="http_get", url="https://status.example.com/x", approval="required")]
    run_id, alert_id, _ = await make_run(session, payments, steps)
    await waiting(session, run_id, 0, StepStatus.AWAITING_APPROVAL)
    await login(client, lead)
    assert (await client.post(decision_url(alert_id, 0), json=APPROVE)).status_code == 200
    http = FakeHttp()

    claimed = await worker.process_due(sessionmaker, Integrations(http=http, ops=SimulatedOps()), NOW)

    assert claimed == 1
    assert http.calls == ["https://status.example.com/x"]
    (step,) = await rows(session, run_id)
    assert (step.status, step.run_at) == (StepStatus.SUCCEEDED, None)
    assert (await client.get(run_url(alert_id))).json()["steps"][0]["status"] == "succeeded"


async def test_the_executor_moves_an_answered_step_on_to_the_approval_gate(
    client: AsyncClient,
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    payments: Team,
    member: User,
) -> None:
    step = TypeAdapter(Step).validate_python({"action": "restart_service", "service": "billing", "if": "is it bad?"})
    run_id, alert_id, _ = await make_run(session, payments, [step])
    await waiting(session, run_id, 0, StepStatus.AWAITING_ANSWER)
    await login(client, member)
    assert (await client.post(decision_url(alert_id, 0), json={"decision": "yes"})).status_code == 200

    claimed = await worker.process_due(sessionmaker, Integrations(http=FakeHttp(), ops=SimulatedOps()), NOW)

    assert claimed == 1
    (stored,) = await rows(session, run_id)
    assert (stored.status, stored.guard_answered, stored.approved, stored.run_at) == (
        StepStatus.AWAITING_APPROVAL,
        True,
        False,
        None,
    )


@pytest.mark.parametrize(("role", "decision"), [("member", "approve"), ("member", "reject"), ("viewer", "done")])
async def test_a_role_without_the_right_gets_403(
    client: AsyncClient,
    session: AsyncSession,
    payments: Team,
    member: User,
    viewer: User,
    role: str,
    decision: str,
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(
        session, run_id, 1, StepStatus.AWAITING_MANUAL if decision == "done" else StepStatus.AWAITING_APPROVAL
    )
    await login(client, member if role == "member" else viewer)

    response = await client.post(decision_url(alert_id, 1), json={"decision": decision})

    assert response.status_code == 403
    assert (await rows(session, run_id))[1].status in {StepStatus.AWAITING_MANUAL, StepStatus.AWAITING_APPROVAL}
    assert await decisions(session, alert_id) == []


@pytest.mark.parametrize(
    ("decision", "status", "action", "to"),
    [
        (StepDecisionKind.APPROVE, StepStatus.AWAITING_APPROVAL, AuditAction.STEP_APPROVED, StepStatus.PENDING),
        (StepDecisionKind.REJECT, StepStatus.AWAITING_APPROVAL, AuditAction.STEP_REJECTED, StepStatus.SKIPPED),
        (StepDecisionKind.YES, StepStatus.AWAITING_ANSWER, AuditAction.STEP_ANSWERED, StepStatus.PENDING),
        (StepDecisionKind.NO, StepStatus.AWAITING_ANSWER, AuditAction.STEP_ANSWERED, StepStatus.SKIPPED),
        (StepDecisionKind.DONE, StepStatus.AWAITING_MANUAL, AuditAction.STEP_DONE, StepStatus.SUCCEEDED),
    ],
)
async def test_each_kind_of_decision_audits_its_action_on_the_alert(
    client: AsyncClient,
    session: AsyncSession,
    payments: Team,
    admin: User,
    decision: StepDecisionKind,
    status: StepStatus,
    action: AuditAction,
    to: StepStatus,
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 1, status)
    await login(client, admin)

    response = await client.post(decision_url(alert_id, 1), json={"decision": decision.value})

    assert response.status_code == 200
    (entry,) = await decisions(session, alert_id)
    assert (entry.action, entry.entity_type, entry.actor_user_id) == (action, AuditEntityType.ALERT, admin.id)
    expected: dict[str, JsonValue] = {
        "run_id": str(run_id),
        "index": 1,
        "decision": decision.value,
        "from": status.value,
        "to": to.value,
        "note": None,
    }
    assert entry.data == expected


async def test_a_lead_of_an_escalated_team_approves(
    client: AsyncClient, session: AsyncSession, payments: Team, search: Team, outsider: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await session.execute(update(Alert).where(Alert.id == alert_id).values(escalated_team_ids=[search.id]))
    await waiting(session, run_id, 0, StepStatus.AWAITING_APPROVAL)
    await login(client, outsider)

    assert (await client.post(decision_url(alert_id, 0), json=APPROVE)).status_code == 200


async def test_the_owner_of_a_personal_rule_decides_on_their_own_alert(
    client: AsyncClient, session: AsyncSession, payments: Team
) -> None:
    owner = await make_user(session, "owner")
    run_id, alert_id = await make_personal_run(session, payments, owner)
    await waiting(session, run_id, 0, StepStatus.AWAITING_APPROVAL)
    await login(client, owner)

    response = await client.post(decision_url(alert_id, 0), json=APPROVE)

    assert response.status_code == 200
    (entry,) = await decisions(session, alert_id)
    assert (entry.actor_user_id, entry.team_id) == (owner.id, None)


async def test_an_admin_approves(client: AsyncClient, session: AsyncSession, payments: Team, admin: User) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 0, StepStatus.AWAITING_APPROVAL)
    await login(client, admin)

    assert (await client.post(decision_url(alert_id, 0), json=APPROVE)).status_code == 200


async def test_a_decision_that_does_not_fit_the_status_gets_409(
    client: AsyncClient, session: AsyncSession, payments: Team, lead: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 0, StepStatus.AWAITING_APPROVAL)
    await login(client, lead)

    response = await client.post(decision_url(alert_id, 0), json={"decision": "yes"})

    assert response.status_code == 409
    assert "awaiting_approval" in response.json()["detail"]
    assert "yes" in response.json()["detail"]


@pytest.mark.parametrize("status", [StepStatus.RUNNING, StepStatus.SUCCEEDED, StepStatus.PENDING])
async def test_a_step_that_is_not_waiting_gets_409(
    client: AsyncClient, session: AsyncSession, payments: Team, lead: User, status: StepStatus
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 1, status)
    await login(client, lead)

    for decision in StepDecisionKind:
        assert (await client.post(decision_url(alert_id, 1), json={"decision": decision})).status_code == 409


async def test_a_second_decision_on_the_same_step_gets_409(
    client: AsyncClient, session: AsyncSession, payments: Team, lead: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 0, StepStatus.AWAITING_APPROVAL)
    await login(client, lead)
    assert (await client.post(decision_url(alert_id, 0), json=APPROVE)).status_code == 200

    response = await client.post(decision_url(alert_id, 0), json={"decision": "reject"})

    assert response.status_code == 409
    assert (await rows(session, run_id))[0].status is StepStatus.PENDING
    assert len(await decisions(session, alert_id)) == 1


async def test_an_index_out_of_range_gets_404(
    client: AsyncClient, session: AsyncSession, payments: Team, lead: User
) -> None:
    _, alert_id, _ = await make_run(session, payments)
    await login(client, lead)

    assert (await client.post(decision_url(alert_id, 3), json=APPROVE)).status_code == 404


async def test_deciding_on_an_alert_of_another_team_gets_404(
    client: AsyncClient, session: AsyncSession, payments: Team, outsider: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 0, StepStatus.AWAITING_APPROVAL)
    await login(client, outsider)

    assert (await client.post(decision_url(alert_id, 0), json=APPROVE)).status_code == 404


async def test_an_alert_without_a_run_gets_404_on_decision(
    client: AsyncClient, session: AsyncSession, payments: Team, lead: User
) -> None:
    opened = await open_alert(session, payments, None)
    await login(client, lead)

    assert (await client.post(decision_url(opened.alert_id, 0), json=APPROVE)).status_code == 404


async def test_the_step_runs_stay_untouched_by_a_rejected_decision(
    client: AsyncClient, session: AsyncSession, payments: Team, member: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await waiting(session, run_id, 0, StepStatus.AWAITING_APPROVAL)
    await login(client, member)

    assert (await client.post(decision_url(alert_id, 0), json=APPROVE)).status_code == 403

    stored = list(
        await session.scalars(select(StepRun).where(StepRun.run_id == run_id).execution_options(populate_existing=True))
    )
    assert {(s.status, s.approved, s.decided_by, s.decided_at) for s in stored} == {
        (StepStatus.AWAITING_APPROVAL, False, None, None),
        (StepStatus.PENDING, False, None, None),
    }


# --- Resolve -----------------------------------------------------------------------------------------------------


async def run_audit(
    session: AsyncSession, alert_id: uuid.UUID
) -> list[tuple[AuditAction, uuid.UUID | None, JsonValue]]:
    """The run's step and finish entries on the alert: action, actor and step index."""
    entries = await session.scalars(
        select(AuditEntry)
        .where(
            AuditEntry.entity_id == alert_id,
            AuditEntry.action.in_([AuditAction.STEP_SKIPPED, AuditAction.RUNBOOK_RUN_FINISHED]),
        )
        .order_by(AuditEntry.id)
    )
    return [(entry.action, entry.actor_user_id, entry.data.get("index")) for entry in entries]


async def test_resolving_skips_the_unfinished_steps_and_finishes_the_run(
    client: AsyncClient, session: AsyncSession, payments: Team, member: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    # A succeeded retry that still watches the alert's occurrences.
    await set_step(session, run_id, 0, status=StepStatus.SUCCEEDED, run_at=NOW)
    await waiting(session, run_id, 1, StepStatus.AWAITING_MANUAL)
    await login(client, member)

    assert (await client.post(f"/alerts/{alert_id}/resolve", json={})).status_code == 200

    steps = await rows(session, run_id)
    assert [(s.status, s.run_at) for s in steps] == [
        (StepStatus.SUCCEEDED, None),
        (StepStatus.SKIPPED, None),
        (StepStatus.SKIPPED, None),
    ]
    assert await run_audit(session, alert_id) == [
        (AuditAction.STEP_SKIPPED, member.id, 1),
        (AuditAction.STEP_SKIPPED, member.id, 2),
        (AuditAction.RUNBOOK_RUN_FINISHED, member.id, None),
    ]
    assert (await client.post(decision_url(alert_id, 1), json={"decision": "done"})).status_code == 409


async def test_resolving_after_the_run_finished_audits_nothing_more(
    client: AsyncClient, session: AsyncSession, payments: Team, member: User
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    for index in range(3):
        await set_step(session, run_id, index, status=StepStatus.SUCCEEDED, run_at=None)
    await login(client, member)

    assert (await client.post(f"/alerts/{alert_id}/resolve", json={})).status_code == 200

    assert await run_audit(session, alert_id) == []


async def test_an_outcome_written_after_the_resolve_is_dropped(
    client: AsyncClient,
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    payments: Team,
    member: User,
) -> None:
    run_id, alert_id, _ = await make_run(session, payments)
    await set_step(session, run_id, 0, run_at=NOW)
    async with sessionmaker() as claiming, claiming.begin():
        (job,) = await claim_due_steps(claiming, 1, NOW)
    await login(client, member)
    assert (await client.post(f"/alerts/{alert_id}/resolve", json={})).status_code == 200

    async with sessionmaker() as completing, completing.begin():
        await complete_step(completing, job, StepSucceeded(result="200"), NOW)

    assert [s.status for s in await rows(session, run_id)] == [StepStatus.SKIPPED] * 3
