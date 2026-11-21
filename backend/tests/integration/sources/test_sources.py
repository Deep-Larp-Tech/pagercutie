import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.tokens import hash_token
from pagercutie.event_schemas.models import EventSchema
from pagercutie.sources.models import Source
from pagercutie.sources.schemas import FixedSchema, SeverityMapping, SourceType
from pagercutie.sources.service import load_ingest_sources
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


@dataclass(frozen=True)
class World:
    team: Team
    schema: EventSchema
    source: Source
    member: User
    viewer: User
    outsider: User


def user(name: str) -> User:
    return User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=GlobalRole.USER)


def new_source(team: Team, schema: EventSchema, slug: str, *, enabled: bool = True, token: str | None = None) -> Source:
    return Source(
        slug=slug,
        name=slug,
        type=SourceType.WEBHOOK,
        team_id=team.id,
        schema_resolution=FixedSchema(mode="fixed", schema_id=schema.id),
        severity=SeverityMapping(),
        enabled=enabled,
        token_hash=hash_token(token) if token else None,
    )


@pytest.fixture
async def world(session: AsyncSession) -> World:
    team, other = Team(slug="payments", name="Payments"), Team(slug="search", name="Search")
    member, viewer, outsider = user("maria"), user("victor"), user("otto")
    session.add_all([team, other, member, viewer, outsider])
    await session.flush()
    schema = EventSchema(name="payment", version=1, team_id=team.id, json_schema={"type": "object"})
    session.add_all(
        [
            schema,
            Membership(team_id=team.id, user_id=member.id, role=TeamRole.MEMBER),
            Membership(team_id=team.id, user_id=viewer.id, role=TeamRole.VIEWER),
            Membership(team_id=other.id, user_id=outsider.id, role=TeamRole.LEAD),
        ]
    )
    await session.flush()
    source = new_source(team, schema, "payments-webhook")
    session.add(source)
    await session.flush()
    return World(team, schema, source, member, viewer, outsider)


async def login(client: AsyncClient, who: User) -> None:
    assert (await client.post("/auth/login", json={"email": who.email})).status_code == 200


def create_body(world: World, slug: str = "payments-ws", source_type: str = "websocket") -> dict[str, object]:
    return {
        "slug": slug,
        "name": "Payments",
        "type": source_type,
        "team_id": str(world.team.id),
        "schema_resolution": {"mode": "fixed", "schema_id": str(world.schema.id)},
    }


@pytest.mark.parametrize(
    ("source_type", "ingest_url"),
    [("webhook", "/ingest/new-source"), ("websocket", "/ingest/new-source/ws")],
)
async def test_member_creates_a_source_that_has_no_token_yet(
    client: AsyncClient, world: World, source_type: str, ingest_url: str
) -> None:
    await login(client, world.member)

    response = await client.post("/sources", json=create_body(world, "new-source", source_type))

    assert response.status_code == 201
    body = response.json()
    assert body["ingest_url"] == ingest_url
    assert body["has_token"] is False
    assert body["severity"]["default"] == "info"


async def test_viewer_cannot_create_or_rotate(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)

    assert (await client.post("/sources", json=create_body(world))).status_code == 403
    assert (await client.post(f"/sources/{world.source.id}/token")).status_code == 403


async def test_sources_of_other_teams_are_invisible(client: AsyncClient, world: World) -> None:
    await login(client, world.outsider)

    assert (await client.get(f"/sources/{world.source.id}")).status_code == 404
    assert (await client.get("/sources")).json() == []
    assert (await client.patch(f"/sources/{world.source.id}", json={"enabled": False})).status_code == 404


async def test_duplicate_slug_conflicts_and_leaves_the_transaction_usable(client: AsyncClient, world: World) -> None:
    await login(client, world.member)

    response = await client.post("/sources", json=create_body(world, slug="payments-webhook"))

    assert response.status_code == 409
    assert [s["slug"] for s in (await client.get("/sources")).json()] == ["payments-webhook"]


@pytest.mark.parametrize(
    ("change", "loc"),
    [
        ({"type": "protobuf"}, ["body", "type"]),
        ({"schema_resolution": {"mode": "fixed", "schema_id": str(uuid.uuid7())}}, ["body", "schema_resolution"]),
    ],
)
async def test_unsupported_type_and_unknown_schema_are_rejected(
    client: AsyncClient, world: World, change: dict[str, object], loc: list[str]
) -> None:
    await login(client, world.member)

    response = await client.post("/sources", json=create_body(world) | change)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == loc


async def test_rotated_token_is_returned_once_and_only_its_hash_is_stored(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)

    token = (await client.post(f"/sources/{world.source.id}/token")).json()["token"]

    assert (await client.get(f"/sources/{world.source.id}")).json()["has_token"] is True
    await session.refresh(world.source)
    assert world.source.token_hash == hash_token(token)


async def test_ingest_loads_enabled_sources_with_a_token_and_skips_unreadable_rows(
    session: AsyncSession, world: World
) -> None:
    good = new_source(world.team, world.schema, "good", token="a")
    unreadable = new_source(world.team, world.schema, "unreadable", token="b")
    session.add_all([good, unreadable, new_source(world.team, world.schema, "disabled", enabled=False, token="c")])
    await session.flush()
    await session.execute(
        text("""UPDATE sources SET severity = '{"default": "nope"}' WHERE id = :id"""), {"id": unreadable.id}
    )

    sources = await load_ingest_sources(session)

    assert [(s.slug, s.token_hash) for s in sources] == [("good", hash_token("a"))]
