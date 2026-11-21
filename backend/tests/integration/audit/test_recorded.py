"""Every implemented change writes one audit entry in its own transaction (RUN-5)."""

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction, AuditEntityType
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users import service as users
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


@dataclass
class World:
    admin: User
    lead: User
    member: User
    team: Team


@pytest.fixture
async def world(session: AsyncSession) -> World:
    team = Team(slug="payments", name="Payments")
    admin = User(email="admin@example.com", display_name="Admin", timezone="UTC", role=GlobalRole.ADMIN)
    lead = User(email="lead@example.com", display_name="Lead", timezone="UTC", role=GlobalRole.USER)
    member = User(email="member@example.com", display_name="Member", timezone="UTC", role=GlobalRole.USER)
    session.add_all([team, admin, lead, member])
    await session.flush()
    session.add_all(
        [
            Membership(team_id=team.id, user_id=lead.id, role=TeamRole.LEAD),
            Membership(team_id=team.id, user_id=member.id, role=TeamRole.MEMBER),
        ]
    )
    await session.flush()
    return World(admin=admin, lead=lead, member=member, team=team)


async def login(client: AsyncClient, user: User) -> None:
    assert (await client.post("/auth/login", json={"email": user.email})).status_code == 200


async def entries(session: AsyncSession) -> list[AuditEntry]:
    # One outer transaction per test, so every entry has the same `at`; UUIDv7 ids keep the write order.
    return list(await session.scalars(select(AuditEntry).order_by(AuditEntry.id)))


async def only_entry(session: AsyncSession) -> AuditEntry:
    (entry,) = await entries(session)
    return entry


async def test_creating_updating_and_deleting_a_user_is_audited(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.admin)

    created = await client.post("/users", json={"email": "new@example.com", "display_name": "New", "timezone": "UTC"})
    user_id = uuid.UUID(created.json()["id"])
    await client.patch(f"/users/{user_id}", json={"display_name": "Renamed", "timezone": "UTC"})
    await client.delete(f"/users/{user_id}")

    create, update, delete = await entries(session)
    assert [e.action for e in (create, update, delete)] == [
        AuditAction.USER_CREATED,
        AuditAction.USER_UPDATED,
        AuditAction.USER_DELETED,
    ]
    assert {(e.actor_user_id, e.entity_type, e.entity_id, e.team_id) for e in (create, update, delete)} == {
        (world.admin.id, AuditEntityType.USER, user_id, None)
    }
    assert create.data == {"email": "new@example.com", "display_name": "New", "role": "user"}
    # Only changed fields: the timezone was sent unchanged.
    assert update.data == {"before": {"display_name": "New"}, "after": {"display_name": "Renamed"}}
    assert delete.data == {"email": "new@example.com", "display_name": "Renamed"}


async def test_an_update_that_changes_nothing_is_not_audited(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)

    assert (await client.patch(f"/users/{world.member.id}", json={"display_name": "Member"})).status_code == 200

    assert await entries(session) == []


async def test_user_channel_preferences_are_audited_with_both_values(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)
    rules = [{"min_severity": "error", "channels": ["sms"], "window": None}]

    await client.put(f"/users/{world.member.id}/channel-preferences", json={"rules": rules})

    entry = await only_entry(session)
    assert entry.action is AuditAction.USER_CHANNEL_PREFERENCES_UPDATED
    assert entry.actor_user_id == world.member.id
    assert entry.data == {"before": {"rules": []}, "after": {"rules": rules}}


async def test_a_refused_change_writes_no_entry(client: AsyncClient, session: AsyncSession, world: World) -> None:
    await login(client, world.member)

    response = await client.post("/users", json={"email": "new@example.com", "display_name": "New", "timezone": "UTC"})

    assert response.status_code == 403
    assert await entries(session) == []


async def test_team_changes_are_audited_on_the_team(client: AsyncClient, session: AsyncSession, world: World) -> None:
    await login(client, world.admin)

    created = await client.post("/teams", json={"slug": "search", "name": "Search"})
    team_id = uuid.UUID(created.json()["id"])
    await client.patch(f"/teams/{team_id}", json={"description": "Finds things"})
    await client.delete(f"/teams/{team_id}")

    create, update, delete = await entries(session)
    assert [e.action for e in (create, update, delete)] == [
        AuditAction.TEAM_CREATED,
        AuditAction.TEAM_UPDATED,
        AuditAction.TEAM_DELETED,
    ]
    # The team's own id, so its members can read its history.
    assert {(e.entity_type, e.entity_id, e.team_id) for e in (create, update, delete)} == {
        (AuditEntityType.TEAM, team_id, team_id)
    }
    assert create.data == {"slug": "search", "name": "Search", "description": None}
    assert update.data == {"before": {"description": None}, "after": {"description": "Finds things"}}
    assert delete.data == {"slug": "search", "name": "Search"}


async def test_membership_changes_are_audited_by_kind(client: AsyncClient, session: AsyncSession, world: World) -> None:
    await login(client, world.lead)
    url = f"/teams/{world.team.id}/members/{world.admin.id}"

    await client.put(url, json={"role": "viewer"})
    await client.put(url, json={"role": "viewer"})
    await client.put(url, json={"role": "member"})
    await client.delete(url)

    added, changed, removed = await entries(session)
    user_id = str(world.admin.id)
    assert (added.action, added.data) == (AuditAction.TEAM_MEMBER_ADDED, {"user_id": user_id, "role": "viewer"})
    assert (changed.action, changed.data) == (
        AuditAction.TEAM_MEMBER_ROLE_CHANGED,
        {"user_id": user_id, "before": {"role": "viewer"}, "after": {"role": "member"}},
    )
    assert (removed.action, removed.data) == (
        AuditAction.TEAM_MEMBER_REMOVED,
        {"user_id": user_id, "role": "member"},
    )
    assert {(e.actor_user_id, e.entity_id, e.team_id) for e in (added, changed, removed)} == {
        (world.lead.id, world.team.id, world.team.id)
    }


async def test_rotation_and_team_preferences_are_audited_with_both_values(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.lead)
    rules = [{"min_severity": "critical", "channels": ["phone"], "window": None}]

    await client.put(f"/teams/{world.team.id}/rotation", json={"user_ids": [str(world.lead.id)]})
    await client.put(f"/teams/{world.team.id}/rotation", json={"user_ids": [str(world.member.id)]})
    await client.put(f"/teams/{world.team.id}/channel-preferences", json={"rules": rules})

    first, second, preferences = await entries(session)
    schedule = {"handoff_day": "mon", "handoff_time": "09:00:00", "timezone": "UTC"}
    assert first.action is AuditAction.TEAM_ROTATION_UPDATED
    assert first.data == {"before": None, "after": {"user_ids": [str(world.lead.id)], **schedule}}
    assert second.data == {
        "before": {"user_ids": [str(world.lead.id)], **schedule},
        "after": {"user_ids": [str(world.member.id)], **schedule},
    }
    assert preferences.action is AuditAction.TEAM_CHANNEL_PREFERENCES_UPDATED
    assert preferences.data == {"before": {"rules": []}, "after": {"rules": rules}}


async def test_source_changes_are_audited_without_the_token(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)
    body = {"slug": "payments-ws", "name": "Payments", "type": "websocket", "team_id": str(world.team.id)}

    source_id = (await client.post("/sources", json=body)).json()["id"]
    await client.patch(f"/sources/{source_id}", json={"enabled": False})
    token = (await client.post(f"/sources/{source_id}/token")).json()["token"]
    await client.delete(f"/sources/{source_id}")

    create, update, rotate, delete = await entries(session)
    assert [e.action for e in (create, update, rotate, delete)] == [
        AuditAction.SOURCE_CREATED,
        AuditAction.SOURCE_UPDATED,
        AuditAction.SOURCE_TOKEN_ROTATED,
        AuditAction.SOURCE_DELETED,
    ]
    assert {(e.actor_user_id, e.entity_id, e.team_id) for e in (create, update, rotate, delete)} == {
        (world.member.id, uuid.UUID(source_id), world.team.id)
    }
    assert create.data["slug"] == "payments-ws"
    assert update.data == {"before": {"enabled": True}, "after": {"enabled": False}}
    assert rotate.data == {}
    assert delete.data["enabled"] is False
    assert all(token not in str(e.data) for e in (create, update, rotate, delete))


async def test_creating_an_event_schema_version_is_audited(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)
    body = {"name": "payment-failed", "version": 1, "team_id": str(world.team.id), "json_schema": {"type": "object"}}

    schema_id = (await client.post("/event-schemas", json=body)).json()["id"]

    entry = await only_entry(session)
    assert (entry.action, entry.entity_type) == (AuditAction.EVENT_SCHEMA_CREATED, AuditEntityType.EVENT_SCHEMA)
    assert (entry.entity_id, entry.team_id) == (uuid.UUID(schema_id), world.team.id)
    assert entry.data == {"name": "payment-failed", "version": 1}


async def test_bootstrapping_the_admin_is_audited_as_the_system(session: AsyncSession) -> None:
    assert await users.bootstrap_admin(session, "Root@Example.com")

    entry = await only_entry(session)
    assert (entry.actor_user_id, entry.action) == (None, AuditAction.USER_CREATED)
    assert entry.data == {"email": "root@example.com", "role": "admin"}


async def test_promoting_an_existing_user_to_admin_is_audited_as_an_update(session: AsyncSession) -> None:
    user = User(email="root@example.com", display_name="Root", timezone="UTC", role=GlobalRole.USER)
    session.add(user)
    await session.flush()

    assert await users.bootstrap_admin(session, "root@example.com")

    entry = await only_entry(session)
    assert (entry.actor_user_id, entry.action, entry.entity_id) == (None, AuditAction.USER_UPDATED, user.id)
    assert entry.data == {"before": {"role": "user"}, "after": {"role": "admin"}}
