import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit.models import AuditEntry
from pagercutie.core.enums import Severity
from pagercutie.rules.ast import Exists
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, TeamRecipient
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookRead
from pagercutie.runbooks.steps import Manual
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

SETTLEMENT_TIMEOUT = """\
runbook: settlement-timeout
matches:
  type: WORKFLOW_FAILED
  "error.code": TIMEOUT
steps:
  - check: "Is counterparty-service healthy?"
    action: http_get
    url: "http://counterparty-service/health"
  - action: retry_workflow
    workflowId: "{{workflowId}}"
    approval: none
  - if: "retry fails twice"
    action: escalate
    team: counterparty-support
    approval: required
"""

SETTLEMENT_ATTACH = {
    "op": "and",
    "args": [
        {"op": "eq", "field": "payload.type", "value": "WORKFLOW_FAILED"},
        {"op": "eq", "field": "payload.error.code", "value": "TIMEOUT"},
    ],
}


@dataclass
class World:
    payments: Team
    search: Team
    admin: User
    lead: User
    member: User
    viewer: User
    outsider: User


async def make_user(session: AsyncSession, name: str, role: GlobalRole = GlobalRole.USER) -> User:
    user = User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=role)
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def world(session: AsyncSession) -> World:
    payments = Team(slug="payments", name="Payments")
    search = Team(slug="search", name="Search")
    session.add_all([payments, search])
    await session.flush()
    admin = await make_user(session, "admin", GlobalRole.ADMIN)
    lead = await make_user(session, "lead")
    member = await make_user(session, "member")
    viewer = await make_user(session, "viewer")
    outsider = await make_user(session, "outsider")
    session.add_all(
        [
            Membership(team_id=payments.id, user_id=lead.id, role=TeamRole.LEAD),
            Membership(team_id=payments.id, user_id=member.id, role=TeamRole.MEMBER),
            Membership(team_id=payments.id, user_id=viewer.id, role=TeamRole.VIEWER),
            Membership(team_id=search.id, user_id=outsider.id, role=TeamRole.MEMBER),
        ]
    )
    await session.flush()
    return World(payments, search, admin, lead, member, viewer, outsider)


async def login(client: AsyncClient, user: User) -> None:
    response = await client.post("/auth/login", json={"email": user.email})
    assert response.status_code == 200


def body(world: World, **overrides: object) -> dict[str, object]:
    return {
        "slug": "settlement-timeout",
        "title": "Settlement timeout",
        "team_id": str(world.payments.id),
        "format": "structured",
        "original": SETTLEMENT_TIMEOUT,
        **overrides,
    }


async def create(client: AsyncClient, world: World, **overrides: object) -> dict[str, object]:
    response = await client.post("/runbooks", json=body(world, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def audit_entries(session: AsyncSession, entity_id: str) -> list[AuditEntry]:
    entries = await session.scalars(
        select(AuditEntry).where(AuditEntry.entity_id == uuid.UUID(entity_id)).order_by(AuditEntry.id)
    )
    return list(entries)


# --- create -----------------------------------------------------------------------------------------------------


async def test_member_creates_the_settlement_runbook_with_parsed_steps(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)

    created = await create(client, world)

    assert created["slug"] == "settlement-timeout"
    assert created["format"] == "structured"
    assert created["original"] == SETTLEMENT_TIMEOUT
    assert created["attach"] == SETTLEMENT_ATTACH
    assert created["steps"] == [
        {
            "action": "http_get",
            "check": "Is counterparty-service healthy?",
            "if": None,
            "approval": None,
            "url": "http://counterparty-service/health",
        },
        {"action": "retry_workflow", "check": None, "if": None, "approval": "none", "workflowId": "{{workflowId}}"},
        {
            "action": "escalate",
            "check": None,
            "if": {"step": 1, "failures_gte": 2},
            "approval": "required",
            "team": "counterparty-support",
        },
    ]
    (entry,) = await audit_entries(session, str(created["id"]))
    assert (entry.action, entry.entity_type, entry.actor_user_id, entry.team_id) == (
        "runbook.created",
        "runbook",
        world.member.id,
        world.payments.id,
    )
    assert entry.data == {
        "after": {
            "title": "Settlement timeout",
            "format": "structured",
            "original": SETTLEMENT_TIMEOUT,
            "attach": SETTLEMENT_ATTACH,
        }
    }


async def test_explicit_attach_overrides_matches(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    attach = {"op": "exists", "field": "payload.workflowId"}

    created = await create(client, world, attach=attach)

    assert created["attach"] == attach


@pytest.mark.parametrize(
    ("format", "original", "texts"),
    [
        ("markdown", "# T\n1. Check\n2. Fix\n", ["Check", "Fix"]),
        ("text", "Restart the pricing engine.", ["Restart the pricing engine."]),
        ("link", "https://wiki.example.com/rb", ["Open the runbook: https://wiki.example.com/rb"]),
    ],
)
async def test_other_formats_become_manual_steps(
    client: AsyncClient, world: World, format: str, original: str, texts: list[str]
) -> None:
    await login(client, world.member)

    created = RunbookRead.model_validate(
        await create(client, world, slug=f"rb-{format}", format=format, original=original)
    )

    assert created.steps == [Manual(action="manual", text=text) for text in texts]
    assert created.attach is None


async def test_invalid_structured_runbook_answers_422(client: AsyncClient, world: World) -> None:
    await login(client, world.member)

    response = await client.post("/runbooks", json=body(world, original="runbook: x\nsteps: [\n"))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "original"]


async def test_structured_runbook_named_differently_from_its_slug_answers_422(
    client: AsyncClient, world: World
) -> None:
    await login(client, world.member)

    response = await client.post("/runbooks", json=body(world, slug="other-slug"))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "original", "runbook"]


async def test_duplicate_slug_answers_409(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    await create(client, world)

    response = await client.post("/runbooks", json=body(world))

    assert response.status_code == 409


async def test_unknown_team_answers_404_for_an_admin(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)

    response = await client.post("/runbooks", json=body(world, team_id=str(uuid.uuid4())))

    assert response.status_code == 404


@pytest.mark.parametrize("who", ["viewer", "outsider"])
async def test_viewer_and_outsider_cannot_create(client: AsyncClient, world: World, who: str) -> None:
    await login(client, getattr(world, who))

    response = await client.post("/runbooks", json=body(world))

    assert response.status_code == 403


# --- parse ------------------------------------------------------------------------------------------------------


async def test_parse_previews_without_saving(client: AsyncClient, session: AsyncSession, world: World) -> None:
    await login(client, world.outsider)
    original = SETTLEMENT_TIMEOUT.replace("retry fails twice", "it looks bad")

    response = await client.post("/runbooks/parse", json={"format": "structured", "original": original})

    assert response.status_code == 200
    result = response.json()
    assert result["attach"] == SETTLEMENT_ATTACH
    assert result["steps"][2]["if"] == "it looks bad"
    assert result["warnings"] == ["Step 3: the guard 'it looks bad' is not recognised; a human answers it"]
    assert await session.scalar(select(Runbook.id)) is None


async def test_parse_rejects_invalid_structured_runbook(client: AsyncClient, world: World) -> None:
    await login(client, world.member)

    response = await client.post("/runbooks/parse", json={"format": "structured", "original": "steps: []"})

    assert response.status_code == 422


# --- list and get -----------------------------------------------------------------------------------------------


async def test_list_shows_the_runbooks_of_the_users_teams(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    payments = await create(client, world)
    search = await create(client, world, slug="search-rb", team_id=str(world.search.id), format="text", original="x")

    await login(client, world.viewer)
    assert [r["id"] for r in (await client.get("/runbooks")).json()] == [payments["id"]]

    await login(client, world.admin)
    assert [r["id"] for r in (await client.get("/runbooks")).json()] == [payments["id"], search["id"]]
    filtered = (await client.get("/runbooks", params={"team_id": str(world.search.id)})).json()
    assert [r["id"] for r in filtered] == [search["id"]]


async def test_get_answers_404_outside_the_team(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    created = await create(client, world)

    assert (await client.get(f"/runbooks/{created['id']}")).json() == created
    await login(client, world.outsider)
    assert (await client.get(f"/runbooks/{created['id']}")).status_code == 404


# --- update -----------------------------------------------------------------------------------------------------


async def test_update_reparses_and_audits_the_changed_fields(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)
    created = await create(client, world, slug="rb", format="text", original="Restart it.")

    response = await client.patch(
        f"/runbooks/{created['id']}", json={"format": "markdown", "original": "- Check\n- Restart\n"}
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == created["title"]
    assert [s["text"] for s in updated["steps"]] == ["Check", "Restart"]
    assert updated["updated_at"] >= created["updated_at"]
    _, entry = await audit_entries(session, str(created["id"]))
    assert entry.action == "runbook.updated"
    assert entry.data == {
        "before": {"format": "text", "original": "Restart it."},
        "after": {"format": "markdown", "original": "- Check\n- Restart\n"},
    }


async def test_update_of_the_title_keeps_the_steps(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    created = await create(client, world)

    updated = (await client.patch(f"/runbooks/{created['id']}", json={"title": "Renamed"})).json()

    assert updated["title"] == "Renamed"
    assert updated["steps"] == created["steps"]
    assert updated["attach"] == created["attach"]


async def test_update_without_changes_writes_no_audit_entry(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)
    created = await create(client, world)

    response = await client.patch(f"/runbooks/{created['id']}", json={"title": created["title"]})

    assert response.status_code == 200
    assert len(await audit_entries(session, str(created["id"]))) == 1


async def test_update_keeps_an_explicit_attach_when_the_new_yaml_has_no_matches(
    client: AsyncClient, world: World
) -> None:
    await login(client, world.member)
    attach = {"op": "exists", "field": "payload.workflowId"}
    created = await create(client, world, attach=attach)
    original = "runbook: settlement-timeout\nsteps:\n  - action: wait\n    seconds: 5\n"

    updated = (await client.patch(f"/runbooks/{created['id']}", json={"original": original})).json()

    assert updated["attach"] == attach
    assert updated["steps"] == [{"action": "wait", "check": None, "if": None, "approval": None, "seconds": 5}]


async def test_update_with_invalid_yaml_changes_nothing(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    created = await create(client, world)

    response = await client.patch(f"/runbooks/{created['id']}", json={"original": "runbook: [\n"})

    assert response.status_code == 422
    assert (await client.get(f"/runbooks/{created['id']}")).json() == created


async def test_viewer_cannot_update_and_outsider_gets_404(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    created = await create(client, world)

    await login(client, world.viewer)
    assert (await client.patch(f"/runbooks/{created['id']}", json={"title": "X"})).status_code == 403
    await login(client, world.outsider)
    assert (await client.patch(f"/runbooks/{created['id']}", json={"title": "X"})).status_code == 404


# --- delete -----------------------------------------------------------------------------------------------------


async def test_delete_hides_the_runbook_detaches_rules_and_frees_the_slug(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)
    created = await create(client, world)
    runbook_id = uuid.UUID(str(created["id"]))
    rule = Rule(
        name="Settlement failures",
        enabled=True,
        team_id=world.payments.id,
        user_id=None,
        schema_ids=[],
        condition=Exists(op="exists", field="payload.workflowId"),
        dedup=Dedup(),
        routing=Routing(recipients=[TeamRecipient(type="team", team_id=world.payments.id)]),
        presentation=Presentation(title="Failed", severity=Severity.ERROR, colour=Colour.RED),
        runbook_id=runbook_id,
    )
    session.add(rule)
    await session.flush()

    response = await client.delete(f"/runbooks/{runbook_id}")

    assert response.status_code == 204
    assert (await client.get(f"/runbooks/{runbook_id}")).status_code == 404
    assert (await client.get("/runbooks")).json() == []
    assert (await client.delete(f"/runbooks/{runbook_id}")).status_code == 404
    await session.refresh(rule)
    assert rule.runbook_id is None
    row = await session.scalar(select(Runbook).where(Runbook.id == runbook_id))
    assert row is not None
    assert row.deleted_at is not None
    *_, entry = await audit_entries(session, str(runbook_id))
    assert entry.action == "runbook.deleted"
    assert entry.data == {
        "slug": "settlement-timeout",
        "title": "Settlement timeout",
        "detached_rule_ids": [str(rule.id)],
    }
    await create(client, world)


async def test_viewer_cannot_delete(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    created = await create(client, world)
    await login(client, world.viewer)

    assert (await client.delete(f"/runbooks/{created['id']}")).status_code == 403
