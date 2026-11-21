"""Every user change through the API writes one audit entry in the same transaction (RUN-5)."""

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit.models import AuditEntry
from pagercutie.core.tokens import hash_token
from pagercutie.sources.models import Source
from pagercutie.sources.schemas import SeverityMapping, SourceType
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


@dataclass(frozen=True)
class World:
    team: Team
    source: Source
    admin: User
    lead: User
    member: User
    viewer: User


def _user(name: str, role: GlobalRole = GlobalRole.USER) -> User:
    return User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=role)


@pytest.fixture
async def world(session: AsyncSession) -> World:
    team = Team(slug="payments", name="Payments")
    admin, lead, member, viewer = _user("ada", GlobalRole.ADMIN), _user("lena"), _user("maria"), _user("victor")
    session.add_all([team, admin, lead, member, viewer])
    await session.flush()
    session.add_all(
        [
            Membership(team_id=team.id, user_id=lead.id, role=TeamRole.LEAD),
            Membership(team_id=team.id, user_id=member.id, role=TeamRole.MEMBER),
            Membership(team_id=team.id, user_id=viewer.id, role=TeamRole.VIEWER),
        ]
    )
    source = Source(
        slug="payments-webhook",
        name="Payments webhook",
        type=SourceType.WEBHOOK,
        team_id=team.id,
        severity=SeverityMapping(),
        enabled=True,
        token_hash=hash_token("old-token"),
    )
    session.add(source)
    await session.flush()
    return World(team, source, admin, lead, member, viewer)


async def login(client: AsyncClient, user: User) -> None:
    assert (await client.post("/auth/login", json={"email": user.email})).status_code == 200


async def entries(session: AsyncSession, action: str) -> list[AuditEntry]:
    """Entries with `action`, oldest first (UUIDv7 ids sort in creation order)."""
    return list(await session.scalars(select(AuditEntry).where(AuditEntry.action == action).order_by(AuditEntry.id)))


# --- Auth ------------------------------------------------------------------------------------------------------


async def test_login_and_logout_are_audited_on_the_user(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)
    assert (await client.post("/auth/logout")).status_code == 204

    (logged_in,) = await entries(session, "user.logged_in")
    (logged_out,) = await entries(session, "user.logged_out")
    for entry in (logged_in, logged_out):
        assert entry.actor_user_id == world.member.id
        assert entry.entity_type == "user"
        assert entry.entity_id == world.member.id
        assert entry.team_id is None
        assert entry.data == {}


async def test_failed_login_writes_nothing(client: AsyncClient, session: AsyncSession, world: World) -> None:
    assert (await client.post("/auth/login", json={"email": "nobody@example.com"})).status_code == 404

    assert await entries(session, "user.logged_in") == []


# --- Users -----------------------------------------------------------------------------------------------------


async def test_user_create_update_and_delete_are_audited(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.admin)

    created = (await client.post("/users", json={"email": "Nina@Example.com", "display_name": "Nina"})).json()
    user_id = uuid.UUID(created["id"])
    assert (await client.patch(f"/users/{user_id}", json={"role": "admin"})).status_code == 200
    assert (await client.patch(f"/users/{user_id}", json={})).status_code == 200
    assert (await client.delete(f"/users/{user_id}")).status_code == 204

    (create,) = await entries(session, "user.created")
    assert (create.actor_user_id, create.entity_type, create.entity_id) == (world.admin.id, "user", user_id)
    assert create.team_id is None
    assert create.data["email"] == "nina@example.com"
    assert create.data["role"] == "user"
    (update,) = await entries(session, "user.updated")
    assert update.data == {"role": "admin"}
    (delete,) = await entries(session, "user.deleted")
    assert delete.entity_id == user_id


# --- Teams -----------------------------------------------------------------------------------------------------


async def test_team_create_update_and_delete_are_audited(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.admin)

    created = (await client.post("/teams", json={"slug": "search", "name": "Search"})).json()
    team_id = uuid.UUID(created["id"])
    assert (await client.patch(f"/teams/{team_id}", json={"name": "Search & Discovery"})).status_code == 200
    assert (await client.delete(f"/teams/{team_id}")).status_code == 204

    (create,) = await entries(session, "team.created")
    assert (create.entity_type, create.entity_id, create.team_id) == ("team", team_id, team_id)
    assert create.data == {"slug": "search", "name": "Search", "description": None}
    (update,) = await entries(session, "team.updated")
    assert update.data == {"name": "Search & Discovery"}
    (delete,) = await entries(session, "team.deleted")
    assert delete.data == {"slug": "search"}


async def test_membership_changes_are_audited_on_the_team(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    newcomer = _user("nora")
    session.add(newcomer)
    await session.flush()
    url = f"/teams/{world.team.id}/members/{newcomer.id}"
    await login(client, world.lead)

    assert (await client.put(url, json={"role": "viewer"})).status_code == 200
    assert (await client.put(url, json={"role": "member"})).status_code == 200
    assert (await client.put(url, json={"role": "member"})).status_code == 200
    assert (await client.delete(url)).status_code == 204

    (added,) = await entries(session, "team.member_added")
    assert (added.actor_user_id, added.entity_type, added.entity_id) == (world.lead.id, "team", world.team.id)
    assert added.data == {"user_id": str(newcomer.id), "from": None, "to": "viewer"}
    (changed,) = await entries(session, "team.member_role_changed")
    assert changed.data == {"user_id": str(newcomer.id), "from": "viewer", "to": "member"}
    (removed,) = await entries(session, "team.member_removed")
    assert removed.data == {"user_id": str(newcomer.id), "role": "member"}


async def test_rotation_change_is_audited(client: AsyncClient, session: AsyncSession, world: World) -> None:
    await login(client, world.lead)

    response = await client.put(f"/teams/{world.team.id}/rotation", json={"user_ids": [str(world.member.id)]})

    assert response.status_code == 200
    (entry,) = await entries(session, "team.rotation_set")
    assert entry.team_id == world.team.id
    assert entry.data["user_ids"] == [str(world.member.id)]


async def test_channel_preference_changes_are_audited(client: AsyncClient, session: AsyncSession, world: World) -> None:
    await login(client, world.lead)

    assert (await client.put(f"/teams/{world.team.id}/channel-preferences", json={"rules": []})).status_code == 200
    assert (await client.put(f"/users/{world.lead.id}/channel-preferences", json={"rules": []})).status_code == 200

    (team,) = await entries(session, "team.channel_preferences_set")
    assert (team.entity_type, team.entity_id, team.team_id) == ("team", world.team.id, world.team.id)
    assert team.data == {"rules": []}
    (user,) = await entries(session, "user.channel_preferences_set")
    assert (user.actor_user_id, user.entity_type, user.entity_id) == (world.lead.id, "user", world.lead.id)
    assert user.team_id is None


# --- Sources ---------------------------------------------------------------------------------------------------


async def test_source_changes_are_audited_without_the_token(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    url = f"/sources/{world.source.id}"
    await login(client, world.member)

    body = {"slug": "payments-ws", "name": "Payments WS", "type": "websocket", "team_id": str(world.team.id)}
    created = (await client.post("/sources", json=body)).json()
    assert (await client.patch(url, json={"enabled": False})).status_code == 200
    token = (await client.post(f"{url}/token")).json()["token"]
    assert (await client.delete(url)).status_code == 204

    (create,) = await entries(session, "source.created")
    assert (create.entity_type, create.entity_id) == ("source", uuid.UUID(created["id"]))
    assert create.team_id == world.team.id
    assert create.data["slug"] == "payments-ws"
    (update,) = await entries(session, "source.updated")
    assert update.data == {"enabled": False}
    (rotate,) = await entries(session, "source.token_rotated")
    assert rotate.data == {}
    assert token not in str(rotate.data)
    (delete,) = await entries(session, "source.deleted")
    assert (delete.entity_id, delete.data) == (world.source.id, {"slug": "payments-webhook"})


async def test_rejected_change_writes_nothing(client: AsyncClient, session: AsyncSession, world: World) -> None:
    await login(client, world.viewer)

    assert (await client.patch(f"/sources/{world.source.id}", json={"enabled": False})).status_code == 403

    assert await entries(session, "source.updated") == []


# --- Event schemas ---------------------------------------------------------------------------------------------


async def test_event_schema_creation_is_audited(client: AsyncClient, session: AsyncSession, world: World) -> None:
    await login(client, world.member)
    body = {"name": "settlement", "version": 1, "team_id": str(world.team.id), "json_schema": {"type": "object"}}

    created = (await client.post("/event-schemas", json=body)).json()

    (entry,) = await entries(session, "event_schema.created")
    assert (entry.entity_type, entry.entity_id) == ("event_schema", uuid.UUID(created["id"]))
    assert entry.team_id == world.team.id
    assert entry.data == {"name": "settlement", "version": 1}


# --- Who reads the new entries ---------------------------------------------------------------------------------


async def test_team_members_read_team_entries_but_not_user_entries(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    assert (await client.patch(f"/sources/{world.source.id}", json={"name": "Renamed"})).status_code == 200

    actions = {item["action"] for item in (await client.get("/audit")).json()}

    assert "source.updated" in actions
    assert "user.logged_in" not in actions
