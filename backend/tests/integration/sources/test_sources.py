import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.db import NotifyChannel
from pagercutie.core.tokens import hash_token
from pagercutie.sources import service
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
    other: Team
    source: Source
    admin: User
    lead: User
    member: User
    viewer: User
    outsider: User


def user(name: str, role: GlobalRole = GlobalRole.USER) -> User:
    return User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=role)


def new_source(
    team: Team,
    slug: str,
    *,
    source_type: SourceType = SourceType.WEBHOOK,
    enabled: bool = True,
    token: str | None = None,
) -> Source:
    return Source(
        slug=slug,
        name=slug,
        type=source_type,
        team_id=team.id,
        severity=SeverityMapping(),
        enabled=enabled,
        token_hash=hash_token(token) if token else None,
    )


@pytest.fixture
async def world(session: AsyncSession) -> World:
    team, other = Team(slug="payments", name="Payments"), Team(slug="search", name="Search")
    admin = user("ada", GlobalRole.ADMIN)
    lead, member, viewer, outsider = user("lena"), user("maria"), user("victor"), user("otto")
    session.add_all([team, other, admin, lead, member, viewer, outsider])
    await session.flush()
    session.add_all(
        [
            Membership(team_id=team.id, user_id=lead.id, role=TeamRole.LEAD),
            Membership(team_id=team.id, user_id=member.id, role=TeamRole.MEMBER),
            Membership(team_id=team.id, user_id=viewer.id, role=TeamRole.VIEWER),
            Membership(team_id=other.id, user_id=outsider.id, role=TeamRole.LEAD),
        ]
    )
    await session.flush()
    source = new_source(team, "payments-webhook")
    session.add(source)
    await session.flush()
    return World(team, other, source, admin, lead, member, viewer, outsider)


@pytest.fixture
def notifications(monkeypatch: pytest.MonkeyPatch) -> list[NotifyChannel]:
    sent: list[NotifyChannel] = []

    async def record(session: AsyncSession, channel: NotifyChannel) -> None:
        sent.append(channel)

    monkeypatch.setattr(service, "notify", record)
    return sent


async def login(client: AsyncClient, who: User) -> None:
    assert (await client.post("/auth/login", json={"email": who.email})).status_code == 200


def create_body(
    world: World, slug: str = "payments-ws", source_type: str = "websocket", team_id: uuid.UUID | None = None
) -> dict[str, object]:
    return {
        "slug": slug,
        "name": "Payments",
        "type": source_type,
        "team_id": str(team_id or world.team.id),
    }


async def create(client: AsyncClient, world: World, **overrides: object) -> dict[str, object]:
    response = await client.post("/sources", json={**create_body(world), **overrides})
    assert response.status_code == 201, response.text
    return response.json()


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


@pytest.mark.parametrize("who", ["lead", "member", "admin"])
async def test_writers_create_a_source_and_notify_the_replicas(
    client: AsyncClient, world: World, notifications: list[NotifyChannel], who: str
) -> None:
    await login(client, getattr(world, who))

    created = await create(client, world)

    assert created["enabled"] is True
    assert notifications == [NotifyChannel.SOURCES_CHANGED]


@pytest.mark.parametrize("who", ["viewer", "outsider"])
async def test_non_writers_cannot_create_a_source(
    client: AsyncClient, world: World, notifications: list[NotifyChannel], who: str
) -> None:
    await login(client, getattr(world, who))

    assert (await client.post("/sources", json=create_body(world))).status_code == 403
    assert notifications == []


async def test_forbidden_create_does_not_reveal_whether_the_team_exists(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)

    response = await client.post("/sources", json=create_body(world, team_id=uuid.uuid4()))

    assert response.status_code == 403


async def test_admin_creating_for_an_unknown_team_is_not_found(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)

    response = await client.post("/sources", json=create_body(world, team_id=uuid.uuid4()))

    assert response.status_code == 404


async def test_viewer_cannot_create_or_rotate(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)

    assert (await client.post("/sources", json=create_body(world))).status_code == 403
    assert (await client.post(f"/sources/{world.source.id}/token")).status_code == 403


async def test_sources_of_other_teams_are_invisible(client: AsyncClient, world: World) -> None:
    await login(client, world.outsider)

    assert (await client.get(f"/sources/{world.source.id}")).status_code == 404
    assert (await client.get("/sources")).json() == []
    assert (await client.patch(f"/sources/{world.source.id}", json={"enabled": False})).status_code == 404


async def test_duplicate_slug_conflicts_and_leaves_the_transaction_usable(
    client: AsyncClient, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.member)

    response = await client.post("/sources", json=create_body(world, slug="payments-webhook"))

    assert response.status_code == 409
    assert notifications == []
    assert [s["slug"] for s in (await client.get("/sources")).json()] == ["payments-webhook"]


async def test_source_type_without_an_adapter_is_rejected(client: AsyncClient, world: World) -> None:
    await login(client, world.member)

    response = await client.post("/sources", json=create_body(world, source_type="protobuf"))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "type"]


async def test_stored_source_of_a_type_without_an_adapter_is_listed(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    session.add(new_source(world.team, "ledger-grpc", source_type=SourceType.PROTOBUF))
    await session.flush()
    await login(client, world.member)

    response = await client.get("/sources")

    assert response.status_code == 200
    assert [(s["slug"], s["ingest_url"]) for s in response.json()] == [
        ("ledger-grpc", "/ingest/ledger-grpc"),
        ("payments-webhook", "/ingest/payments-webhook"),
    ]


async def test_non_admins_list_only_the_sources_of_their_teams(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    other = await create(client, world, slug="search-webhook", team_id=str(world.other.id))

    await login(client, world.viewer)
    assert [s["id"] for s in (await client.get("/sources")).json()] == [str(world.source.id)]
    assert (await client.get("/sources", params={"team_id": str(world.other.id)})).json() == []

    await login(client, world.admin)
    assert {s["id"] for s in (await client.get("/sources")).json()} == {str(world.source.id), other["id"]}
    filtered = (await client.get("/sources", params={"team_id": str(world.other.id)})).json()
    assert [s["id"] for s in filtered] == [other["id"]]


async def test_list_is_paginated_by_slug(client: AsyncClient, world: World) -> None:
    await login(client, world.lead)
    for slug in ["c-source", "a-source", "b-source"]:
        await create(client, world, slug=slug)

    page = (await client.get("/sources", params={"limit": 2, "offset": 1})).json()

    assert [s["slug"] for s in page] == ["b-source", "c-source"]


async def test_viewer_reads_a_source_but_an_outsider_gets_not_found(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)
    assert (await client.get(f"/sources/{world.source.id}")).json()["slug"] == "payments-webhook"

    await login(client, world.outsider)
    assert (await client.get(f"/sources/{world.source.id}")).status_code == 404
    assert (await client.get(f"/sources/{uuid.uuid4()}")).status_code == 404


async def test_member_updates_only_the_given_fields(
    client: AsyncClient, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.member)

    response = await client.patch(
        f"/sources/{world.source.id}",
        json={"enabled": False, "severity": {"field": "level", "values": {"WARNING": "warn"}, "default": "info"}},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["enabled"] is False
    assert updated["severity"]["values"] == {"WARNING": "warn"}
    assert updated["name"] == world.source.name
    assert notifications == [NotifyChannel.SOURCES_CHANGED]


async def test_viewer_cannot_change_a_source_but_an_outsider_gets_not_found(client: AsyncClient, world: World) -> None:
    url = f"/sources/{world.source.id}"

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
    url = f"/sources/{world.source.id}"

    assert (await client.delete(url)).status_code == 204

    assert (await client.get(url)).status_code == 404
    assert (await client.delete(url)).status_code == 404
    assert notifications == [NotifyChannel.SOURCES_CHANGED]


async def test_rotated_token_is_returned_once_and_only_its_hash_is_stored(
    client: AsyncClient, session: AsyncSession, world: World
) -> None:
    await login(client, world.member)

    token = (await client.post(f"/sources/{world.source.id}/token")).json()["token"]

    assert (await client.get(f"/sources/{world.source.id}")).json()["has_token"] is True
    await session.refresh(world.source)
    assert world.source.token_hash == hash_token(token)


async def test_rotating_again_replaces_the_previous_token(
    client: AsyncClient, session: AsyncSession, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.member)
    url = f"/sources/{world.source.id}/token"
    stored = select(Source.token_hash).where(Source.id == world.source.id)

    first = (await client.post(url)).json()["token"]
    first_hash = await session.scalar(stored)
    second = (await client.post(url)).json()["token"]
    second_hash = await session.scalar(stored)

    assert first != second
    assert first_hash == hash_token(first)
    assert second_hash == hash_token(second) != first_hash
    assert "token" not in (await client.get(f"/sources/{world.source.id}")).json()
    assert notifications == [NotifyChannel.SOURCES_CHANGED] * 2


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
