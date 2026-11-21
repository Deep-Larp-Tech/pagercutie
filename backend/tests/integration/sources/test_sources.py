from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.tokens import hash_token
from pagercutie.sources.models import Source
from pagercutie.sources.schemas import SeverityMapping, SourceType
from pagercutie.sources.service import load_ingest_sources
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


@dataclass(frozen=True)
class World:
    team: Team
    source: Source
    member: User
    viewer: User
    outsider: User


def user(name: str) -> User:
    return User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=GlobalRole.USER)


def new_source(team: Team, slug: str, *, enabled: bool = True, token: str | None = None) -> Source:
    return Source(
        slug=slug,
        name=slug,
        type=SourceType.WEBHOOK,
        team_id=team.id,
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
    session.add_all(
        [
            Membership(team_id=team.id, user_id=member.id, role=TeamRole.MEMBER),
            Membership(team_id=team.id, user_id=viewer.id, role=TeamRole.VIEWER),
            Membership(team_id=other.id, user_id=outsider.id, role=TeamRole.LEAD),
        ]
    )
    await session.flush()
    source = new_source(team, "payments-webhook")
    session.add(source)
    await session.flush()
    return World(team, source, member, viewer, outsider)


async def login(client: AsyncClient, who: User) -> None:
    assert (await client.post("/auth/login", json={"email": who.email})).status_code == 200


def create_body(world: World, slug: str = "payments-ws", source_type: str = "websocket") -> dict[str, object]:
    return {
        "slug": slug,
        "name": "Payments",
        "type": source_type,
        "team_id": str(world.team.id),
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


async def test_source_type_without_an_adapter_is_rejected(client: AsyncClient, world: World) -> None:
    await login(client, world.member)

    response = await client.post("/sources", json=create_body(world, source_type="protobuf"))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "type"]


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
    good = new_source(world.team, "good", token="a")
    unreadable = new_source(world.team, "unreadable", token="b")
    session.add_all([good, unreadable, new_source(world.team, "disabled", enabled=False, token="c")])
    await session.flush()
    await session.execute(
        text("""UPDATE sources SET severity = '{"default": "nope"}' WHERE id = :id"""), {"id": unreadable.id}
    )

    sources = await load_ingest_sources(session)

    assert [(s.slug, s.token_hash) for s in sources] == [("good", hash_token("a"))]
