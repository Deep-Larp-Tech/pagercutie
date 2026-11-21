import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert
from pagercutie.alerts.schemas import AlertStatus
from pagercutie.core.db import NotifyChannel
from pagercutie.core.enums import Severity
from pagercutie.event_schemas.models import EventSchema
from pagercutie.rules import service
from pagercutie.rules.schemas import Colour
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

type Json = dict[str, object]


@dataclass(frozen=True)
class World:
    team: Team
    other: Team
    schema: EventSchema
    runbook: Runbook
    other_runbook: Runbook
    admin: User
    lead: User
    member: User
    viewer: User
    outsider: User
    gone: User


def user(name: str, role: GlobalRole = GlobalRole.USER) -> User:
    return User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=role)


def runbook(team: Team, slug: str) -> Runbook:
    return Runbook(slug=slug, title=slug, team_id=team.id, format=RunbookFormat.TEXT, original="Restart it", steps=[])


@pytest.fixture
async def world(session: AsyncSession) -> World:
    team, other = Team(slug="payments", name="Payments"), Team(slug="search", name="Search")
    admin = user("ada", GlobalRole.ADMIN)
    lead, member, viewer, outsider, gone = user("lena"), user("maria"), user("victor"), user("otto"), user("gone")
    gone.deleted_at = datetime(2026, 11, 20, tzinfo=UTC)
    session.add_all([team, other, admin, lead, member, viewer, outsider, gone])
    await session.flush()
    schema = EventSchema(name="payment", version=1, team_id=other.id, json_schema={"type": "object"})
    own_runbook, other_runbook = runbook(team, "payments-restart"), runbook(other, "search-restart")
    session.add_all(
        [
            Membership(team_id=team.id, user_id=lead.id, role=TeamRole.LEAD),
            Membership(team_id=team.id, user_id=member.id, role=TeamRole.MEMBER),
            Membership(team_id=team.id, user_id=viewer.id, role=TeamRole.VIEWER),
            Membership(team_id=other.id, user_id=outsider.id, role=TeamRole.LEAD),
            Membership(team_id=other.id, user_id=member.id, role=TeamRole.VIEWER),
            schema,
            own_runbook,
            other_runbook,
        ]
    )
    await session.flush()
    return World(team, other, schema, own_runbook, other_runbook, admin, lead, member, viewer, outsider, gone)


@pytest.fixture
def notifications(monkeypatch: pytest.MonkeyPatch) -> list[NotifyChannel]:
    sent: list[NotifyChannel] = []

    async def record(session: AsyncSession, channel: NotifyChannel) -> None:
        sent.append(channel)

    monkeypatch.setattr(service, "notify", record)
    return sent


async def login(client: AsyncClient, who: User) -> None:
    assert (await client.post("/auth/login", json={"email": who.email})).status_code == 200


def team_owner(team: Team) -> Json:
    return {"type": "team", "team_id": str(team.id)}


def user_owner(who: User) -> Json:
    return {"type": "user", "user_id": str(who.id)}


def body(owner: Json, recipients: Sequence[Mapping[str, str]], **overrides: object) -> Json:
    return {
        "name": "Settlement failed",
        "owner": owner,
        "condition": {"op": "eq", "field": "payload.type", "value": "WORKFLOW_FAILED"},
        "routing": {"recipients": recipients},
        "presentation": {"title": "Settlement {{payload.workflowId}} failed", "severity": "critical", "colour": "red"},
        **overrides,
    }


def team_body(world: World, **overrides: object) -> Json:
    return body(team_owner(world.team), [{"type": "on_call", "team_id": str(world.team.id)}], **overrides)


def personal_body(who: User, **overrides: object) -> Json:
    return body(user_owner(who), [{"type": "user", "user_id": str(who.id)}], **overrides)


async def create(client: AsyncClient, data: Json) -> Json:
    response = await client.post("/rules", json=data)
    assert response.status_code == 201, response.text
    return response.json()


def locs(response_json: Json) -> list[list[object]]:
    detail = response_json["detail"]
    assert isinstance(detail, list)
    return [error["loc"] for error in detail]


# --- Create ----------------------------------------------------------------------------------------------------


async def test_member_creates_a_team_rule(
    client: AsyncClient, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.member)

    rule = await create(client, team_body(world, schema_ids=[str(world.schema.id)], runbook_id=str(world.runbook.id)))

    assert rule["owner"] == team_owner(world.team)
    assert rule["enabled"] is True
    assert rule["dedup"] == {"fields": [], "window_s": 300}
    assert rule["schema_ids"] == [str(world.schema.id)]
    assert rule["runbook_id"] == str(world.runbook.id)
    assert notifications == [NotifyChannel.RULES_CHANGED]
    assert (await client.get(f"/rules/{rule['id']}")).json() == rule


@pytest.mark.parametrize("who", ["viewer", "outsider"])
async def test_only_members_and_leads_create_team_rules(client: AsyncClient, world: World, who: str) -> None:
    await login(client, getattr(world, who))

    assert (await client.post("/rules", json=team_body(world))).status_code == 403


async def test_team_rule_for_an_unknown_team_is_404(client: AsyncClient, world: World) -> None:
    await login(client, world.admin)
    owner = {"type": "team", "team_id": str(uuid.uuid7())}

    response = await client.post("/rules", json=team_body(world, owner=owner))

    assert response.status_code == 404


async def test_anyone_creates_a_personal_rule_for_themselves(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)

    rule = await create(client, personal_body(world.viewer))

    assert rule["owner"] == user_owner(world.viewer)


@pytest.mark.parametrize("who", ["member", "admin"])
async def test_nobody_creates_a_personal_rule_for_someone_else(client: AsyncClient, world: World, who: str) -> None:
    await login(client, getattr(world, who))

    assert (await client.post("/rules", json=personal_body(world.viewer))).status_code == 403


# --- Write checks ----------------------------------------------------------------------------------------------


async def test_unknown_and_repeated_schemas_are_rejected(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    known = str(world.schema.id)

    response = await client.post("/rules", json=team_body(world, schema_ids=[known, str(uuid.uuid7()), known]))

    assert response.status_code == 422
    assert locs(response.json()) == [["body", "schema_ids", 1], ["body", "schema_ids", 2]]


async def test_recipients_must_exist(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    recipients = [
        {"type": "user", "user_id": str(world.gone.id)},
        {"type": "team", "team_id": str(uuid.uuid7())},
        {"type": "team", "team_id": str(world.other.id)},
        {"type": "user", "user_id": str(world.outsider.id)},
    ]

    response = await client.post("/rules", json=body(team_owner(world.team), recipients))

    assert response.status_code == 422
    assert locs(response.json()) == [
        ["body", "routing", "recipients", 0, "user_id"],
        ["body", "routing", "recipients", 1, "team_id"],
    ]


async def test_personal_rule_notifies_only_its_owner(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)
    recipients = [{"type": "user", "user_id": str(world.viewer.id)}, {"type": "team", "team_id": str(world.team.id)}]

    response = await client.post("/rules", json=body(user_owner(world.viewer), recipients))

    assert response.status_code == 422
    assert locs(response.json()) == [["body", "routing", "recipients", 1]]


@pytest.mark.parametrize(
    ("runbook", "expected"),
    [("other_runbook", 422), ("missing", 422), ("runbook", 201)],
)
async def test_team_rule_uses_a_runbook_of_its_team(
    client: AsyncClient, world: World, runbook: str, expected: int
) -> None:
    await login(client, world.member)
    runbook_id = str(uuid.uuid7()) if runbook == "missing" else str(getattr(world, runbook).id)

    response = await client.post("/rules", json=team_body(world, runbook_id=runbook_id))

    assert response.status_code == expected
    if expected == 422:
        assert locs(response.json()) == [["body", "runbook_id"]]


async def test_personal_rule_uses_a_runbook_of_a_team_its_owner_sees(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)

    allowed = await client.post("/rules", json=personal_body(world.viewer, runbook_id=str(world.runbook.id)))
    hidden = await client.post("/rules", json=personal_body(world.viewer, runbook_id=str(world.other_runbook.id)))

    assert allowed.status_code == 201
    assert hidden.status_code == 422


@pytest.mark.parametrize(
    "condition",
    [
        {"op": "eq", "field": "payload.a", "value": "x\u0000"},
        {"op": "in", "field": "payload.a", "value": [1, "\u0000"]},
        {"op": "not", "arg": {"op": "glob", "field": "source", "value": "a\u0000*"}},
    ],
)
async def test_nul_in_condition_text_is_rejected(client: AsyncClient, world: World, condition: Json) -> None:
    await login(client, world.member)

    response = await client.post("/rules", json=team_body(world, condition=condition))

    assert response.status_code == 422
    assert locs(response.json()) == [["body", "condition"]]


async def test_condition_deeper_than_the_limit_is_rejected(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    condition: Json = {"op": "exists", "field": "source"}
    for _ in range(32):
        condition = {"op": "not", "arg": condition}

    assert (await client.post("/rules", json=team_body(world, condition=condition))).status_code == 422


# --- Read ------------------------------------------------------------------------------------------------------


async def test_list_shows_visible_rules_in_creation_order(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    team_rule = await create(client, team_body(world))
    member_personal = await create(client, personal_body(world.member))
    await login(client, world.outsider)
    other_rule = await create(client, body(team_owner(world.other), [{"type": "team", "team_id": str(world.other.id)}]))
    outsider_personal = await create(client, personal_body(world.outsider))

    async def ids(who: User, query: str = "") -> list[object]:
        await login(client, who)
        response = await client.get(f"/rules{query}")
        assert response.status_code == 200
        return [rule["id"] for rule in response.json()]

    assert await ids(world.member) == [team_rule["id"], member_personal["id"], other_rule["id"]]
    assert await ids(world.viewer) == [team_rule["id"]]
    assert await ids(world.admin) == [team_rule["id"], member_personal["id"], other_rule["id"], outsider_personal["id"]]
    assert await ids(world.admin, f"?team_id={world.team.id}") == [team_rule["id"]]
    assert await ids(world.admin, f"?user_id={world.outsider.id}") == [outsider_personal["id"]]
    assert await ids(world.member, f"?user_id={world.outsider.id}") == []
    assert await ids(world.admin, "?limit=2&offset=1") == [member_personal["id"], other_rule["id"]]


async def test_get_hides_rules_the_user_cannot_see(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    team_rule = await create(client, team_body(world))
    personal = await create(client, personal_body(world.member))

    await login(client, world.outsider)
    assert (await client.get(f"/rules/{team_rule['id']}")).status_code == 404
    assert (await client.get(f"/rules/{personal['id']}")).status_code == 404
    await login(client, world.viewer)
    assert (await client.get(f"/rules/{team_rule['id']}")).status_code == 200
    assert (await client.get(f"/rules/{personal['id']}")).status_code == 404
    await login(client, world.admin)
    assert (await client.get(f"/rules/{personal['id']}")).status_code == 200
    assert (await client.get(f"/rules/{uuid.uuid7()}")).status_code == 404


# --- Update ----------------------------------------------------------------------------------------------------


async def test_patch_changes_only_the_fields_sent(
    client: AsyncClient, world: World, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.member)
    rule = await create(
        client, team_body(world, description="Old", runbook_id=str(world.runbook.id), schema_ids=[str(world.schema.id)])
    )
    notifications.clear()

    response = await client.patch(
        f"/rules/{rule['id']}", json={"name": None, "description": None, "enabled": False, "dedup": {"window_s": 60}}
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["name"] == rule["name"]
    assert updated["description"] is None
    assert updated["enabled"] is False
    assert updated["dedup"] == {"fields": [], "window_s": 60}
    assert updated["runbook_id"] == str(world.runbook.id)
    assert updated["schema_ids"] == [str(world.schema.id)]
    assert updated["created_at"] == rule["created_at"]
    assert notifications == [NotifyChannel.RULES_CHANGED]

    cleared = await client.patch(f"/rules/{rule['id']}", json={"runbook_id": None})
    assert cleared.json()["runbook_id"] is None


async def test_patch_checks_the_fields_sent_against_the_owner(client: AsyncClient, world: World) -> None:
    await login(client, world.viewer)
    rule = await create(client, personal_body(world.viewer))

    response = await client.patch(
        f"/rules/{rule['id']}",
        json={"routing": {"recipients": [{"type": "on_call", "team_id": str(world.team.id)}]}},
    )

    assert response.status_code == 422
    assert locs(response.json()) == [["body", "routing", "recipients", 0]]


async def test_owner_is_permanent(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    rule = await create(client, team_body(world))

    response = await client.patch(f"/rules/{rule['id']}", json={"owner": user_owner(world.member)})

    assert response.status_code == 422


async def test_only_editors_patch(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    team_rule = await create(client, team_body(world))
    personal = await create(client, personal_body(world.member))

    await login(client, world.viewer)
    assert (await client.patch(f"/rules/{team_rule['id']}", json={"enabled": False})).status_code == 403
    await login(client, world.admin)
    assert (await client.patch(f"/rules/{personal['id']}", json={"enabled": False})).status_code == 403
    assert (await client.patch(f"/rules/{team_rule['id']}", json={"enabled": False})).status_code == 200


# --- Delete ----------------------------------------------------------------------------------------------------


async def test_delete_is_soft_and_keeps_alerts(
    client: AsyncClient, world: World, session: AsyncSession, notifications: list[NotifyChannel]
) -> None:
    await login(client, world.member)
    rule = await create(client, team_body(world))
    now = datetime.now(UTC)
    session.add(
        Alert(
            rule_id=uuid.UUID(str(rule["id"])),
            team_id=world.team.id,
            fingerprint="0" * 64,
            status=AlertStatus.OPEN,
            severity=Severity.CRITICAL,
            colour=Colour.RED,
            title="Settlement failed",
            fields=[],
            occurrences=1,
            notified_at=now,
            first_seen_at=now,
            last_seen_at=now,
            escalated_team_ids=[],
            payload={},
        )
    )
    await session.flush()
    notifications.clear()

    response = await client.delete(f"/rules/{rule['id']}")

    assert response.status_code == 204
    assert notifications == [NotifyChannel.RULES_CHANGED]
    assert (await client.get(f"/rules/{rule['id']}")).status_code == 404
    assert (await client.get("/rules")).json() == []
    assert (await client.delete(f"/rules/{rule['id']}")).status_code == 404
    assert await service.list_enabled(session) == []


async def test_only_editors_delete(client: AsyncClient, world: World) -> None:
    await login(client, world.member)
    rule = await create(client, team_body(world))

    await login(client, world.viewer)
    assert (await client.delete(f"/rules/{rule['id']}")).status_code == 403
    await login(client, world.outsider)
    assert (await client.delete(f"/rules/{rule['id']}")).status_code == 404


# --- Test ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("condition", "matched"),
    [
        ({"op": "gte", "field": "severity", "value": "warn"}, True),
        ({"op": "eq", "field": "source", "value": "payments-api"}, True),
        ({"op": "exists", "field": "schema_id"}, True),
        ({"op": "gt", "field": "payload.amount", "value": 1_000_000}, False),
    ],
)
async def test_rule_test_evaluates_against_the_sample_event(
    client: AsyncClient, world: World, condition: Json, matched: bool
) -> None:
    await login(client, world.viewer)

    response = await client.post(
        "/rules/test",
        json={
            "condition": condition,
            "payload": {"amount": 10},
            "source": "payments-api",
            "schema_id": str(world.schema.id),
            "severity": Severity.ERROR,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"matched": matched, "title": None}
