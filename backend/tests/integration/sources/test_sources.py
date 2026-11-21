import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth.service import hash_token
from pagercutie.core.db import NotifyChannel
from pagercutie.event_schemas.models import EventSchema
from pagercutie.sources import service
from pagercutie.sources.models import Source
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


@dataclass
class World:
    payments: Team
    search: Team
    schema: EventSchema
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
    schema = EventSchema(name="settlement", version=1, team_id=payments.id, json_schema={"type": "object"})
    session.add(schema)
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
    return World(payments, search, schema, admin, lead, member, viewer, outsider)


async def login(client: AsyncClient, user: User) -> None:
    response = await client.post("/auth/login", json={"email": user.email})
    assert response.status_code == 200


def body(world: World, **overrides: object) -> dict[str, object]:
    return {
        "slug": "payments-webhook",
        "name": "Payments webhook",
        "type": "webhook",
        "team_id": str(world.payments.id),
        "schema_resolution": {"mode": "fixed", "schema_id": str(world.schema.id)},
        **overrides,
    }


async def create(client: AsyncClient, world: World, **overrides: object) -> dict[str, object]:
    response = await client.post("/sources", json=body(world, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def notifications(monkeypatch: pytest.MonkeyPatch) -> list[NotifyChannel]:
    sent: list[NotifyChannel] = []

    async def record(session: AsyncSession, channel: NotifyChannel) -> None:
        sent.append(channel)

    monkeypatch.setattr(service, "notify", record)
    return sent


@pytest.mark.parametrize("who", ["lead", "member", "admin"])
async def test_writers_create_a_source(
    client: AsyncClient, world: World, notifications: list[NotifyChannel], who: str
) -> None:
    await login(client, getattr(world, who))

    created = await create(client, world)

    assert created["slug"] == "payments-webhook"
    assert created["ingest_url"] == "/ingest/payments-webhook"
    assert created["enabled"] is True
    assert created["severity"] == {"field": None, "values": {}, "default": "info"}
    assert notifications == [NotifyChannel.SCHEMAS_CHANGED]


@pytest.mark.parametrize("who", ["viewer", "outsider"])
async def test_non_writers_cannot_create_a_source(
    client: AsyncClient, world: World, notifications: list[NotifyChannel], who: str
) -> None:
    await login(client, getattr(world, who))

    response = await client.post("/sources", json=body(world))

    assert response.status_code == 403
    assert notifications == []


async def test_forbidden_create_does_not_reveal_whether_the_team_exists(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)

    response = await client.post("/sources", json=body(world, team_id=str(uuid.uuid4())))

    assert response.status_code == 403


async def test_admin_creating_for_an_unknown_team_is_not_found(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)

    response = await client.post("/sources", json=body(world, team_id=str(uuid.uuid4())))

    assert response.status_code == 404


async def test_duplicate_slug_is_a_conflict(
    client: AsyncClient, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.lead)
    await create(client, world)
    notifications.clear()

    response = await client.post("/sources", json=body(world, name="Other"))

    assert response.status_code == 409
    assert notifications == []


async def test_fixed_schema_must_exist(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    resolution = {"mode": "fixed", "schema_id": str(uuid.uuid4())}

    response = await client.post("/sources", json=body(world, schema_resolution=resolution))

    assert response.status_code == 404


async def test_every_discriminator_mapping_schema_must_exist(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    mapping = {"ok": str(world.schema.id), "missing": str(uuid.uuid4())}
    resolution = {"mode": "discriminator", "field": "payload.kind", "mapping": mapping}

    response = await client.post("/sources", json=body(world, schema_resolution=resolution))

    assert response.status_code == 404

    mapping.pop("missing")
    response = await client.post("/sources", json=body(world, schema_resolution=resolution))

    assert response.status_code == 201
    assert response.json()["schema_resolution"]["mapping"] == mapping


async def test_non_admins_list_only_the_sources_of_their_teams(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    mine = await create(client, world)
    other = await create(client, world, slug="search-webhook", team_id=str(world.search.id))

    await login(client, world.viewer)
    visible = (await client.get("/sources")).json()
    assert [source["id"] for source in visible] == [mine["id"]]

    await login(client, world.admin)
    assert {source["id"] for source in (await client.get("/sources")).json()} == {mine["id"], other["id"]}
    filtered = (await client.get("/sources", params={"team_id": str(world.search.id)})).json()
    assert [source["id"] for source in filtered] == [other["id"]]

    await login(client, world.viewer)
    assert (await client.get("/sources", params={"team_id": str(world.search.id)})).json() == []


async def test_list_is_paginated_by_id(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    ids = [(await create(client, world, slug=f"source-{n}"))["id"] for n in range(3)]

    page = (await client.get("/sources", params={"limit": 2, "offset": 1})).json()

    assert [source["id"] for source in page] == ids[1:]


async def test_viewer_reads_a_source_but_an_outsider_gets_not_found(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    created = await create(client, world)

    await login(client, world.viewer)
    assert (await client.get(f"/sources/{created['id']}")).json() == created

    await login(client, world.outsider)
    assert (await client.get(f"/sources/{created['id']}")).status_code == 404
    assert (await client.get(f"/sources/{uuid.uuid4()}")).status_code == 404


async def test_member_updates_only_the_given_fields(
    client: AsyncClient, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.member)
    created = await create(client, world)
    notifications.clear()

    response = await client.patch(
        f"/sources/{created['id']}",
        json={"enabled": False, "severity": {"field": "level", "values": {"WARNING": "warn"}, "default": "info"}},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["enabled"] is False
    assert updated["severity"]["values"] == {"WARNING": "warn"}
    assert updated["name"] == created["name"]
    assert updated["schema_resolution"] == created["schema_resolution"]
    assert notifications == [NotifyChannel.SCHEMAS_CHANGED]


async def test_empty_update_changes_nothing_and_sends_no_notification(
    client: AsyncClient, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.member)
    created = await create(client, world)
    notifications.clear()

    response = await client.patch(f"/sources/{created['id']}", json={})

    assert response.json() == created
    assert notifications == []


async def test_update_validates_the_new_schema_resolution(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    created = await create(client, world)

    response = await client.patch(
        f"/sources/{created['id']}",
        json={"schema_resolution": {"mode": "fixed", "schema_id": str(uuid.uuid4())}},
    )

    assert response.status_code == 404


async def test_viewer_cannot_change_a_source_but_an_outsider_gets_not_found(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    created = await create(client, world)
    url = f"/sources/{created['id']}"

    await login(client, world.viewer)
    assert (await client.patch(url, json={"enabled": False})).status_code == 403
    assert (await client.delete(url)).status_code == 403
    assert (await client.post(f"{url}/token")).status_code == 403

    await login(client, world.outsider)
    assert (await client.patch(url, json={"enabled": False})).status_code == 404
    assert (await client.delete(url)).status_code == 404
    assert (await client.post(f"{url}/token")).status_code == 404


async def test_delete_removes_the_source(client: AsyncClient, world: World, notifications: list[NotifyChannel]) -> None:
    await login(client, world.lead)
    created = await create(client, world)
    notifications.clear()

    assert (await client.delete(f"/sources/{created['id']}")).status_code == 204

    assert (await client.get(f"/sources/{created['id']}")).status_code == 404
    assert (await client.delete(f"/sources/{created['id']}")).status_code == 404
    assert notifications == [NotifyChannel.SCHEMAS_CHANGED]


async def test_rotating_the_token_stores_only_its_hash_and_replaces_the_previous_one(
    client: AsyncClient, session: AsyncSession, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.member)
    created = await create(client, world)
    source_id = uuid.UUID(str(created["id"]))
    assert await session.scalar(select(Source.token_hash).where(Source.id == source_id)) is None
    notifications.clear()

    first = (await client.post(f"/sources/{source_id}/token")).json()["token"]
    first_hash = await session.scalar(select(Source.token_hash).where(Source.id == source_id))
    second = (await client.post(f"/sources/{source_id}/token")).json()["token"]
    second_hash = await session.scalar(select(Source.token_hash).where(Source.id == source_id))

    assert first != second
    assert first_hash == hash_token(first) and len(first_hash) == 32
    assert second_hash == hash_token(second) != first_hash
    assert "token" not in (await client.get(f"/sources/{source_id}")).json()
    assert notifications == [NotifyChannel.SCHEMAS_CHANGED] * 2
