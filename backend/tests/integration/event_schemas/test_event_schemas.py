import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.db import NotifyChannel
from pagercutie.event_schemas import service
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


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
            Membership(team_id=search.id, user_id=outsider.id, role=TeamRole.LEAD),
        ]
    )
    await session.flush()
    return World(payments, search, admin, lead, member, viewer, outsider)


async def login(client: AsyncClient, user: User) -> None:
    response = await client.post("/auth/login", json={"email": user.email})
    assert response.status_code == 200


def body(team: Team, **overrides: object) -> dict[str, object]:
    return {
        "name": "settlement",
        "version": 1,
        "team_id": str(team.id),
        "description": "Settlement events",
        "json_schema": {"type": "object", "required": ["id"]},
        **overrides,
    }


@pytest.fixture
def notifications(monkeypatch: pytest.MonkeyPatch) -> list[NotifyChannel]:
    sent: list[NotifyChannel] = []

    async def record(session: AsyncSession, channel: NotifyChannel) -> None:
        sent.append(channel)

    monkeypatch.setattr(service, "notify", record)
    return sent


@pytest.mark.parametrize("who", ["lead", "member", "admin"])
async def test_writers_create_a_schema(
    client: AsyncClient, world: World, notifications: list[NotifyChannel], who: str
) -> None:
    await login(client, getattr(world, who))

    response = await client.post("/event-schemas", json=body(world.payments))

    assert response.status_code == 201
    created = response.json()
    assert (created["name"], created["version"], created["team_id"]) == ("settlement", 1, str(world.payments.id))
    assert created["json_schema"] == {"type": "object", "required": ["id"]}
    assert notifications == [NotifyChannel.SCHEMAS_CHANGED]


@pytest.mark.parametrize("who", ["viewer", "outsider"])
async def test_non_writers_cannot_create_a_schema(
    client: AsyncClient, world: World, notifications: list[NotifyChannel], who: str
) -> None:
    await login(client, getattr(world, who))

    response = await client.post("/event-schemas", json=body(world.payments))

    assert response.status_code == 403
    assert notifications == []


async def test_admin_creating_for_an_unknown_team_is_invalid_input(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)

    response = await client.post("/event-schemas", json=body(world.payments, team_id=str(uuid.uuid4())))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "team_id"]


@pytest.mark.parametrize(
    "json_schema", [{"type": "not-a-type"}, {"properties": []}, {"$schema": "http://json-schema.org/draft-07/schema#"}]
)
async def test_invalid_or_non_2020_12_json_schema_is_invalid_input(
    client: AsyncClient, world: World, notifications: list[NotifyChannel], json_schema: dict[str, object]
) -> None:
    await login(client, world.lead)

    response = await client.post("/event-schemas", json=body(world.payments, json_schema=json_schema))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][:2] == ["body", "json_schema"]
    assert notifications == []


async def test_explicit_2020_12_dialect_is_accepted(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    json_schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}

    response = await client.post("/event-schemas", json=body(world.payments, json_schema=json_schema))

    assert response.status_code == 201


async def test_duplicate_name_and_version_is_a_conflict(
    client: AsyncClient, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.lead)
    assert (await client.post("/event-schemas", json=body(world.payments))).status_code == 201
    notifications.clear()

    response = await client.post("/event-schemas", json=body(world.payments))

    assert response.status_code == 409
    assert notifications == []


async def test_any_unused_version_is_accepted(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    assert (await client.post("/event-schemas", json=body(world.payments))).status_code == 201

    response = await client.post("/event-schemas", json=body(world.payments, version=5))

    assert response.status_code == 201


async def test_a_name_belongs_to_one_team(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    assert (await client.post("/event-schemas", json=body(world.payments))).status_code == 201

    await login(client, world.outsider)
    response = await client.post("/event-schemas", json=body(world.search, version=2))

    assert response.status_code == 409


async def test_every_user_reads_every_schema(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    created = (await client.post("/event-schemas", json=body(world.payments))).json()

    await login(client, world.outsider)

    assert (await client.get(f"/event-schemas/{created['id']}")).json() == created
    assert (await client.get(f"/event-schemas/{uuid.uuid4()}")).status_code == 404


async def test_list_is_ordered_by_name_and_version_and_filtered(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    for name, version, team in [
        ("b-event", 1, world.payments),
        ("a-event", 2, world.search),
        ("a-event", 1, world.search),
    ]:
        response = await client.post("/event-schemas", json=body(team, name=name, version=version))
        assert response.status_code == 201

    def pairs(schemas: list[dict[str, object]]) -> list[tuple[object, object]]:
        return [(schema["name"], schema["version"]) for schema in schemas]

    assert pairs((await client.get("/event-schemas")).json()) == [("a-event", 1), ("a-event", 2), ("b-event", 1)]
    assert pairs((await client.get("/event-schemas", params={"name": "b-event"})).json()) == [("b-event", 1)]
    by_team = (await client.get("/event-schemas", params={"team_id": str(world.search.id)})).json()
    assert pairs(by_team) == [("a-event", 1), ("a-event", 2)]
    assert pairs((await client.get("/event-schemas", params={"limit": 1, "offset": 1})).json()) == [("a-event", 2)]


async def test_name_filter_must_be_a_slug(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)

    # Postgres text cannot hold NUL, so an unchecked filter would fail in the query with a 500.
    response = await client.get("/event-schemas", params={"name": "\x00"})

    assert response.status_code == 422


async def create_schema(client: AsyncClient, world: World, json_schema: dict[str, object]) -> str:
    await login(client, world.lead)
    response = await client.post("/event-schemas", json=body(world.payments, json_schema=json_schema))
    assert response.status_code == 201
    return response.json()["id"]


async def test_any_user_validates_a_matching_sample(client: AsyncClient, world: World) -> None:
    schema_id = await create_schema(client, world, {"type": "object", "required": ["id"]})
    await login(client, world.outsider)

    response = await client.post(f"/event-schemas/{schema_id}/validate", json={"payload": {"id": 1}})

    assert response.status_code == 200
    assert response.json() == {"valid": True, "issues": []}


async def test_issues_point_into_the_payload(client: AsyncClient, world: World) -> None:
    schema_id = await create_schema(
        client,
        world,
        {
            "type": "object",
            "required": ["id"],
            "properties": {"a/b~c": {"type": "array", "items": {"type": "string"}}},
        },
    )

    response = await client.post(f"/event-schemas/{schema_id}/validate", json={"payload": {"a/b~c": ["x", 2]}})

    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is False
    assert sorted(issue["path"] for issue in result["issues"]) == ["", "/a~1b~0c/1"]


async def test_issues_are_capped(client: AsyncClient, world: World) -> None:
    schema_id = await create_schema(client, world, {"type": "object", "additionalProperties": {"type": "string"}})
    payload = {f"key{index}": index for index in range(service._MAX_ISSUES + 10)}

    response = await client.post(f"/event-schemas/{schema_id}/validate", json={"payload": payload})

    assert len(response.json()["issues"]) == service._MAX_ISSUES


async def test_validating_against_an_unknown_schema_is_not_found(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)

    response = await client.post(f"/event-schemas/{uuid.uuid4()}/validate", json={"payload": {}})

    assert response.status_code == 404


async def test_a_stored_schema_that_does_not_compile_is_invalid_input(client: AsyncClient, world: World) -> None:
    # Valid against the meta-schema, so create accepts it, but offline compilation cannot resolve the `$ref`.
    schema_id = await create_schema(client, world, {"$ref": "https://example.com/event.json"})

    response = await client.post(f"/event-schemas/{schema_id}/validate", json={"payload": {}})

    assert response.status_code == 422
    assert "The stored schema does not compile" in response.json()["detail"][0]["msg"]
