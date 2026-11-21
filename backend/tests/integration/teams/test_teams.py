import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, RunbookRun
from pagercutie.alerts.schemas import AlertStatus
from pagercutie.core.enums import Severity
from pagercutie.event_schemas.models import EventSchema
from pagercutie.rules.ast import Exists
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, UserRecipient
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


@dataclass
class World:
    team: Team
    admin: User
    lead: User
    member: User
    viewer: User
    outsider: User


async def _user(session: AsyncSession, name: str, role: GlobalRole = GlobalRole.USER) -> User:
    user = User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=role)
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def world(session: AsyncSession) -> World:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    admin = await _user(session, "admin", GlobalRole.ADMIN)
    lead = await _user(session, "lead")
    member = await _user(session, "member")
    viewer = await _user(session, "viewer")
    outsider = await _user(session, "outsider")
    await session.flush()
    session.add_all(
        [
            Membership(team_id=team.id, user_id=lead.id, role=TeamRole.LEAD),
            Membership(team_id=team.id, user_id=member.id, role=TeamRole.MEMBER),
            Membership(team_id=team.id, user_id=viewer.id, role=TeamRole.VIEWER),
        ]
    )
    await session.flush()
    return World(team=team, admin=admin, lead=lead, member=member, viewer=viewer, outsider=outsider)


async def login(client: AsyncClient, user: User) -> None:
    response = await client.post("/auth/login", json={"email": user.email})
    assert response.status_code == 200


async def test_any_authenticated_user_reads_teams(client: AsyncClient, world: World) -> None:
    await login(client, world.outsider)

    listed = await client.get("/teams")
    one = await client.get(f"/teams/{world.team.id}")

    assert [t["slug"] for t in listed.json()] == ["payments"]
    assert one.json()["id"] == str(world.team.id)


async def test_outsiders_cannot_read_members_or_rotation(client: AsyncClient, world: World) -> None:
    await login(client, world.outsider)

    assert (await client.get(f"/teams/{world.team.id}/members")).status_code == 404
    assert (await client.get(f"/teams/{world.team.id}/rotation")).status_code == 404


async def test_any_role_in_the_team_reads_members(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)

    members = await client.get(f"/teams/{world.team.id}/members")

    assert {(m["user"]["email"], m["role"]) for m in members.json()} == {
        ("lead@example.com", "lead"),
        ("member@example.com", "member"),
        ("viewer@example.com", "viewer"),
    }
    ids = [m["user"]["id"] for m in members.json()]
    assert ids == sorted(ids)


async def test_missing_team_is_not_found(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    missing = uuid.uuid4()

    assert (await client.get(f"/teams/{missing}")).status_code == 404
    assert (await client.get(f"/teams/{missing}/members")).status_code == 404
    assert (await client.get(f"/teams/{missing}/rotation")).status_code == 404
    assert (await client.patch(f"/teams/{missing}", json={"name": "X"})).status_code == 404
    assert (await client.delete(f"/teams/{missing}")).status_code == 404
    assert (await client.put(f"/teams/{missing}/members/{world.member.id}", json={"role": "member"})).status_code == 404


async def test_only_admins_create_teams(client: AsyncClient, world: World) -> None:
    body = {"slug": "billing", "name": "Billing"}

    await login(client, world.lead)
    assert (await client.post("/teams", json=body)).status_code == 403

    await login(client, world.admin)
    response = await client.post("/teams", json=body)
    assert response.status_code == 201
    assert response.json()["slug"] == "billing"
    assert response.json()["description"] is None


async def test_duplicate_slug_is_a_conflict(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)

    response = await client.post("/teams", json={"slug": "payments", "name": "Again"})

    assert response.status_code == 409


async def test_lead_or_admin_updates_a_team(client: AsyncClient, world: World) -> None:
    url = f"/teams/{world.team.id}"

    await login(client, world.member)
    assert (await client.patch(url, json={"name": "Nope"})).status_code == 403

    await login(client, world.lead)
    response = await client.patch(url, json={"name": "Payments Core"})
    assert response.status_code == 200
    assert response.json()["name"] == "Payments Core"
    assert response.json()["slug"] == "payments"

    await login(client, world.admin)
    response = await client.patch(url, json={"description": "Money movement"})
    assert response.json()["name"] == "Payments Core"
    assert response.json()["description"] == "Money movement"

    assert (await client.patch(url, json={})).json()["name"] == "Payments Core"


async def test_lead_of_another_team_cannot_update(client: AsyncClient, session: AsyncSession, world: World) -> None:
    other = Team(slug="billing", name="Billing")
    session.add(other)
    await session.flush()
    session.add(Membership(team_id=other.id, user_id=world.outsider.id, role=TeamRole.LEAD))
    await session.flush()
    await login(client, world.outsider)

    response = await client.patch(f"/teams/{world.team.id}", json={"name": "Hijacked"})

    assert response.status_code == 403


async def test_only_admins_delete_teams(client: AsyncClient, session: AsyncSession, world: World) -> None:
    url = f"/teams/{world.team.id}"

    await login(client, world.lead)
    assert (await client.delete(url)).status_code == 403

    await login(client, world.admin)
    assert (await client.delete(url)).status_code == 204
    assert (await client.get(url)).status_code == 404
    assert await session.scalar(select(func.count()).select_from(Membership)) == 0


@pytest.mark.parametrize("owned", ["event_schema", "runbook"])
async def test_team_that_owns_entities_cannot_be_deleted(
    client: AsyncClient, session: AsyncSession, world: World, owned: str
) -> None:
    match owned:
        case "event_schema":
            session.add(EventSchema(name="payment", version=1, team_id=world.team.id, json_schema={"type": "object"}))
        case _:
            session.add(
                Runbook(
                    slug="restart",
                    title="Restart",
                    team_id=world.team.id,
                    format=RunbookFormat.TEXT,
                    original="restart it",
                    attach=None,
                    steps=[],
                )
            )
    await session.flush()
    await login(client, world.admin)

    response = await client.delete(f"/teams/{world.team.id}")

    assert response.status_code == 409
    assert (await client.get(f"/teams/{world.team.id}")).status_code == 200


def _runbook(team: Team, *, deleted: bool) -> Runbook:
    return Runbook(
        slug="restart",
        title="Restart",
        team_id=team.id,
        format=RunbookFormat.TEXT,
        original="restart it",
        attach=None,
        steps=[],
        deleted_at=datetime.now(UTC) if deleted else None,
    )


async def test_team_with_only_deleted_runbooks_is_deleted_with_them(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    session.add(_runbook(world.team, deleted=True))
    await session.flush()
    await login(client, world.admin)

    response = await client.delete(f"/teams/{world.team.id}")

    assert response.status_code == 204
    assert await session.scalar(select(func.count()).select_from(Runbook)) == 0


async def test_team_whose_deleted_runbook_has_runs_cannot_be_deleted(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    runbook = _runbook(world.team, deleted=True)
    rule = Rule(
        name="Personal",
        enabled=True,
        team_id=None,
        user_id=world.member.id,
        schema_ids=[],
        condition=Exists(op="exists", field="payload.id"),
        dedup=Dedup(),
        routing=Routing(recipients=[UserRecipient(type="user", user_id=world.member.id)]),
        presentation=Presentation(title="Failed", severity=Severity.ERROR, colour=Colour.RED),
    )
    session.add_all([runbook, rule])
    await session.flush()
    now = datetime.now(UTC)
    alert = Alert(
        rule_id=rule.id,
        team_id=None,
        fingerprint="f" * 64,
        status=AlertStatus.OPEN,
        severity=Severity.ERROR,
        colour=Colour.RED,
        title="Failed",
        fields=[],
        occurrences=1,
        first_seen_at=now,
        last_seen_at=now,
        notified_at=now,
        escalated_team_ids=[],
        payload={},
    )
    session.add(alert)
    await session.flush()
    session.add(RunbookRun(alert_id=alert.id, runbook_id=runbook.id))
    await session.flush()
    await login(client, world.admin)

    response = await client.delete(f"/teams/{world.team.id}")

    assert response.status_code == 409
    assert (await client.get(f"/teams/{world.team.id}")).status_code == 200


async def test_members_list_excludes_soft_deleted_users(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.admin)
    assert (await client.delete(f"/users/{world.viewer.id}")).status_code == 204
    await login(client, world.lead)

    members = await client.get(f"/teams/{world.team.id}/members")

    assert {m["user"]["email"] for m in members.json()} == {"lead@example.com", "member@example.com"}


async def test_set_member_adds_and_changes_role(client: AsyncClient, world: World) -> None:
    url = f"/teams/{world.team.id}/members/{world.outsider.id}"

    await login(client, world.member)
    assert (await client.put(url, json={"role": "member"})).status_code == 403

    await login(client, world.lead)
    added = await client.put(url, json={"role": "viewer"})
    assert added.status_code == 200
    assert added.json()["user"]["id"] == str(world.outsider.id)
    assert added.json()["role"] == "viewer"

    changed = await client.put(url, json={"role": "member"})
    assert changed.json()["role"] == "member"
    roles = {m["user"]["email"]: m["role"] for m in (await client.get(f"/teams/{world.team.id}/members")).json()}
    assert roles["outsider@example.com"] == "member"
    assert len(roles) == 4


async def test_set_member_with_unknown_or_deleted_user_is_not_found(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    await client.delete(f"/users/{world.outsider.id}")

    deleted = await client.put(f"/teams/{world.team.id}/members/{world.outsider.id}", json={"role": "member"})
    unknown = await client.put(f"/teams/{world.team.id}/members/{uuid.uuid4()}", json={"role": "member"})

    assert deleted.status_code == 404
    assert unknown.status_code == 404


async def test_demoting_the_last_lead_is_invalid(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    url = f"/teams/{world.team.id}/members/{world.lead.id}"

    response = await client.put(url, json={"role": "member"})

    assert response.status_code == 422
    assert (await client.put(url, json={"role": "lead"})).status_code == 200


async def test_a_lead_can_be_demoted_once_another_lead_exists(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    base = f"/teams/{world.team.id}/members"
    assert (await client.put(f"{base}/{world.member.id}", json={"role": "lead"})).status_code == 200

    response = await client.put(f"{base}/{world.lead.id}", json={"role": "member"})

    assert response.status_code == 200


async def test_a_deleted_lead_does_not_count_as_another_lead(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    base = f"/teams/{world.team.id}/members"
    await client.put(f"{base}/{world.member.id}", json={"role": "lead"})
    await client.delete(f"/users/{world.member.id}")

    response = await client.put(f"{base}/{world.lead.id}", json={"role": "viewer"})

    assert response.status_code == 422


async def test_remove_member(client: AsyncClient, world: World) -> None:
    base = f"/teams/{world.team.id}/members"

    await login(client, world.member)
    assert (await client.delete(f"{base}/{world.viewer.id}")).status_code == 403

    await login(client, world.lead)
    assert (await client.delete(f"{base}/{world.viewer.id}")).status_code == 204
    assert (await client.delete(f"{base}/{world.viewer.id}")).status_code == 404
    assert (await client.delete(f"{base}/{world.outsider.id}")).status_code == 404


async def test_removing_the_last_lead_is_a_conflict(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    base = f"/teams/{world.team.id}/members"

    assert (await client.delete(f"{base}/{world.lead.id}")).status_code == 409

    await client.put(f"{base}/{world.member.id}", json={"role": "lead"})
    assert (await client.delete(f"{base}/{world.lead.id}")).status_code == 204


async def test_team_without_rotation_returns_null(client: AsyncClient, world: World) -> None:
    await login(client, world.member)

    response = await client.get(f"/teams/{world.team.id}/rotation")

    assert response.status_code == 200
    assert response.json() is None


async def test_set_rotation_replaces_the_previous_one(client: AsyncClient, world: World) -> None:
    url = f"/teams/{world.team.id}/rotation"
    await login(client, world.member)
    assert (await client.put(url, json={"user_ids": [str(world.member.id)]})).status_code == 403

    await login(client, world.lead)
    first = {
        "user_ids": [str(world.lead.id), str(world.member.id), str(world.lead.id)],
        "handoff_day": "fri",
        "handoff_time": "17:30:00",
        "timezone": "Europe/Prague",
    }
    response = await client.put(url, json=first)
    assert response.status_code == 200
    assert response.json() == first
    assert (await client.get(url)).json() == first

    second = {"user_ids": [str(world.member.id)], "handoff_day": "mon", "handoff_time": "09:00:00", "timezone": "UTC"}
    assert (await client.put(url, json=second)).status_code == 200
    assert (await client.get(url)).json() == second


async def test_rotation_users_must_be_active_leads_or_members(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    await client.delete(f"/users/{world.member.id}")
    ids = [world.lead.id, world.viewer.id, world.outsider.id, world.member.id]

    response = await client.put(f"/teams/{world.team.id}/rotation", json={"user_ids": [str(i) for i in ids]})

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert [e["loc"] for e in errors] == [["body", "user_ids", 1], ["body", "user_ids", 2], ["body", "user_ids", 3]]
    assert (await client.get(f"/teams/{world.team.id}/rotation")).json() is None


async def test_deleting_a_team_removes_its_rotation(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    await client.put(f"/teams/{world.team.id}/rotation", json={"user_ids": [str(world.lead.id)]})

    assert (await client.delete(f"/teams/{world.team.id}")).status_code == 204


async def test_teams_are_paginated_in_id_order(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    for slug in ("a", "b", "c"):
        await client.post("/teams", json={"slug": slug, "name": slug.upper()})

    everything = [t["slug"] for t in (await client.get("/teams")).json()]
    page = [t["slug"] for t in (await client.get("/teams", params={"limit": 2, "offset": 1})).json()]

    assert everything == ["payments", "a", "b", "c"]
    assert page == ["a", "b"]
