import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction, AuditEntityType, entity_type_of
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def entry(
    team_id: uuid.UUID | None,
    minutes: int = 0,
    action: AuditAction = AuditAction.RULE_UPDATED,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> AuditEntry:
    audit_entry = AuditEntry(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type_of(action),
        entity_id=entity_id or uuid.uuid4(),
        team_id=team_id,
        data={},
    )
    audit_entry.at = T0 + timedelta(minutes=minutes)
    return audit_entry


@pytest.fixture
async def payments(session: AsyncSession) -> Team:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    return team


@pytest.fixture
async def search(session: AsyncSession) -> Team:
    team = Team(slug="search", name="Search")
    session.add(team)
    await session.flush()
    return team


@pytest.fixture
async def anna(session: AsyncSession, payments: Team) -> User:
    user = User(email="anna@example.com", display_name="Anna", timezone="UTC", role=GlobalRole.USER)
    session.add(user)
    await session.flush()
    session.add(Membership(team_id=payments.id, user_id=user.id, role=TeamRole.MEMBER))
    await session.flush()
    return user


@pytest.fixture
async def loner(session: AsyncSession) -> User:
    user = User(email="loner@example.com", display_name="Loner", timezone="UTC", role=GlobalRole.USER)
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def admin(session: AsyncSession) -> User:
    user = User(email="admin@example.com", display_name="Admin", timezone="UTC", role=GlobalRole.ADMIN)
    session.add(user)
    await session.flush()
    return user


async def login(client: AsyncClient, user: User) -> None:
    response = await client.post("/auth/login", json={"email": user.email})
    assert response.status_code == 200


async def forget_logins(session: AsyncSession) -> None:
    """Delete the `user.logged_in` entries the tests' logins write, for tests that count every entry an admin sees."""
    await session.execute(delete(AuditEntry).where(AuditEntry.action == AuditAction.USER_LOGGED_IN))


async def test_entries_are_listed_newest_first_with_id_as_tiebreak(
    client: AsyncClient, session: AsyncSession, anna: User, payments: Team
) -> None:
    older, newer = entry(payments.id, 0), entry(payments.id, 5)
    tied_first, tied_second = entry(payments.id, 2), entry(payments.id, 2)
    session.add_all([older, tied_first])
    await session.flush()
    session.add_all([tied_second, newer])
    await session.flush()
    await login(client, anna)

    response = await client.get("/audit")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        str(newer.id),
        str(tied_second.id),
        str(tied_first.id),
        str(older.id),
    ]


async def test_response_carries_the_entry_fields(
    client: AsyncClient, session: AsyncSession, anna: User, payments: Team
) -> None:
    row = entry(payments.id, 0)
    row.actor_user_id = anna.id
    row.data = {"before": {"enabled": True}, "after": {"enabled": False}}
    session.add(row)
    await session.flush()
    await login(client, anna)

    (item,) = (await client.get("/audit")).json()

    assert item == {
        "id": str(row.id),
        "at": "2026-01-01T12:00:00Z",
        "actor_user_id": str(anna.id),
        "actor_name": "Anna",
        "action": "rule.updated",
        "entity_type": "rule",
        "entity_id": str(row.entity_id),
        "team_id": str(payments.id),
        "data": {"before": {"enabled": True}, "after": {"enabled": False}},
    }


async def test_admin_sees_every_entry_including_those_without_a_team(
    client: AsyncClient, session: AsyncSession, admin: User, payments: Team, search: Team
) -> None:
    rows = [entry(payments.id, 1), entry(search.id, 2), entry(None, 3)]
    session.add_all(rows)
    await session.flush()
    await login(client, admin)
    await forget_logins(session)

    response = await client.get("/audit")

    assert {item["id"] for item in response.json()} == {str(row.id) for row in rows}


async def test_member_sees_only_entries_of_their_teams(
    client: AsyncClient, session: AsyncSession, anna: User, payments: Team, search: Team
) -> None:
    visible = entry(payments.id, 1)
    session.add_all([visible, entry(search.id, 2), entry(None, 3)])
    await session.flush()
    await login(client, anna)

    response = await client.get("/audit")

    assert [item["id"] for item in response.json()] == [str(visible.id)]


async def test_user_without_teams_sees_nothing(
    client: AsyncClient, session: AsyncSession, loner: User, payments: Team
) -> None:
    session.add_all([entry(payments.id, 1), entry(None, 2)])
    await session.flush()
    await login(client, loner)

    response = await client.get("/audit")

    assert response.status_code == 200
    assert response.json() == []


async def test_non_admin_filtering_by_a_foreign_team_gets_an_empty_list(
    client: AsyncClient, session: AsyncSession, anna: User, search: Team
) -> None:
    session.add(entry(search.id, 1))
    await session.flush()
    await login(client, anna)

    response = await client.get("/audit", params={"team_id": str(search.id)})

    assert response.status_code == 200
    assert response.json() == []


async def test_filters_narrow_the_visible_entries(
    client: AsyncClient, session: AsyncSession, admin: User, payments: Team, search: Team
) -> None:
    target = uuid.uuid4()
    in_payments_rule = entry(payments.id, 1)
    in_payments_alert = entry(payments.id, 2, AuditAction.ALERT_CREATED, entity_id=target)
    in_search_alert = entry(search.id, 3, AuditAction.ALERT_CREATED)
    session.add_all([in_payments_rule, in_payments_alert, in_search_alert])
    await session.flush()
    await login(client, admin)

    async def ids(**params: str) -> list[str]:
        response = await client.get("/audit", params=params)
        assert response.status_code == 200
        return [item["id"] for item in response.json()]

    assert await ids(team_id=str(payments.id)) == [str(in_payments_alert.id), str(in_payments_rule.id)]
    assert await ids(entity_type="alert") == [str(in_search_alert.id), str(in_payments_alert.id)]
    assert await ids(entity_id=str(target)) == [str(in_payments_alert.id)]
    assert await ids(team_id=str(search.id), entity_type="alert", entity_id=str(target)) == []
    assert await ids(team_id=str(payments.id), entity_type="alert") == [str(in_payments_alert.id)]


async def test_pagination_pages_through_entries_newest_first(
    client: AsyncClient, session: AsyncSession, anna: User, payments: Team
) -> None:
    rows = [entry(payments.id, minute) for minute in range(5)]
    session.add_all(rows)
    await session.flush()
    expected = [str(row.id) for row in reversed(rows)]
    await login(client, anna)

    first = await client.get("/audit", params={"limit": 2})
    second = await client.get("/audit", params={"limit": 2, "offset": 2})
    last = await client.get("/audit", params={"limit": 2, "offset": 4})

    assert [item["id"] for item in first.json()] == expected[:2]
    assert [item["id"] for item in second.json()] == expected[2:4]
    assert [item["id"] for item in last.json()] == expected[4:]


async def test_anonymous_requests_are_rejected(client: AsyncClient) -> None:
    assert (await client.get("/audit")).status_code == 401


async def test_unknown_entity_types_and_actions_are_rejected(client: AsyncClient, admin: User) -> None:
    await login(client, admin)

    assert (await client.get("/audit", params={"entity_type": "widget"})).status_code == 422
    assert (await client.get("/audit", params={"action": "rule.exploded"})).status_code == 422


async def test_system_entries_have_no_actor_name(
    client: AsyncClient, session: AsyncSession, anna: User, payments: Team
) -> None:
    session.add(entry(payments.id, 0))
    await session.flush()
    await login(client, anna)

    (item,) = (await client.get("/audit")).json()

    assert item["actor_user_id"] is None
    assert item["actor_name"] is None


async def test_a_soft_deleted_actor_keeps_their_name(
    client: AsyncClient, session: AsyncSession, admin: User, anna: User, payments: Team
) -> None:
    session.add(entry(payments.id, 0, actor_user_id=anna.id))
    anna.deleted_at = T0
    await session.flush()
    await login(client, admin)
    await forget_logins(session)

    (item,) = (await client.get("/audit")).json()

    assert item["actor_name"] == "Anna"


async def test_actor_action_and_time_filters_narrow_the_entries(
    client: AsyncClient, session: AsyncSession, admin: User, anna: User, payments: Team
) -> None:
    by_system = entry(payments.id, 1, AuditAction.ALERT_CREATED)
    by_anna = entry(payments.id, 2, AuditAction.ALERT_ACKNOWLEDGED, actor_user_id=anna.id)
    by_admin = entry(payments.id, 3, AuditAction.RULE_UPDATED, actor_user_id=admin.id)
    without_team = entry(None, 4, AuditAction.USER_CREATED, actor_user_id=admin.id)
    session.add_all([by_system, by_anna, by_admin, without_team])
    await session.flush()
    await login(client, admin)
    await forget_logins(session)

    async def ids(params: dict[str, str | list[str]]) -> list[str]:
        response = await client.get("/audit", params=params)
        assert response.status_code == 200
        return [item["id"] for item in response.json()]

    assert await ids({"actor_user_id": str(anna.id)}) == [str(by_anna.id)]
    assert await ids({"system": "true"}) == [str(by_system.id)]
    assert await ids({"action": ["alert.created", "alert.acknowledged"]}) == [str(by_anna.id), str(by_system.id)]
    assert await ids({"without_team": "true"}) == [str(without_team.id)]
    since, until = (T0 + timedelta(minutes=2)).isoformat(), (T0 + timedelta(minutes=4)).isoformat()
    assert await ids({"since": since, "until": until}) == [str(by_admin.id), str(by_anna.id)]


@pytest.mark.parametrize(
    "params",
    [
        {"system": "true", "actor_user_id": str(uuid.uuid4())},
        {"without_team": "true", "team_id": str(uuid.uuid4())},
        {"since": T0.isoformat(), "until": T0.isoformat()},
        {"until": "0.5"},
    ],
)
async def test_contradicting_filters_are_rejected(client: AsyncClient, admin: User, params: dict[str, str]) -> None:
    await login(client, admin)

    assert (await client.get("/audit", params=params)).status_code == 422


async def test_postgres_enum_labels_match_the_python_enums(session: AsyncSession) -> None:
    # `alembic check` misses added enum values (ADR-0031); a new member needs an `ADD VALUE` migration.
    actions = await session.scalar(text("SELECT enum_range(NULL::audit_action)::text[]"))
    entity_types = await session.scalar(text("SELECT enum_range(NULL::audit_entity_type)::text[]"))

    assert actions == [action.value for action in AuditAction]
    assert entity_types == [entity_type.value for entity_type in AuditEntityType]
