import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

PREFERENCES = {
    "rules": [
        {
            "min_severity": "critical",
            "channels": ["email", "sms"],
            "window": {"days": ["mon", "tue"], "start": "08:00:00", "end": "20:00:00"},
        },
        {"min_severity": "info", "channels": ["ui"], "window": None},
    ]
}


async def _user(session: AsyncSession, name: str, role: GlobalRole = GlobalRole.USER) -> User:
    user = User(email=f"{name}@example.com", display_name=name, timezone="UTC", role=role)
    session.add(user)
    await session.flush()
    return user


async def _login(client: AsyncClient, user: User) -> None:
    assert (await client.post("/auth/login", json={"email": user.email})).status_code == 200


async def test_new_user_has_empty_preferences(client: AsyncClient, session: AsyncSession) -> None:
    anna = await _user(session, "anna")
    await _login(client, anna)

    response = await client.get(f"/users/{anna.id}/channel-preferences")

    assert response.status_code == 200
    assert response.json() == {"rules": []}


async def test_put_replaces_the_preferences(client: AsyncClient, session: AsyncSession) -> None:
    anna = await _user(session, "anna")
    url = f"/users/{anna.id}/channel-preferences"
    await _login(client, anna)

    first = await client.put(url, json=PREFERENCES)
    second = await client.put(url, json={"rules": [PREFERENCES["rules"][1]]})

    assert first.status_code == 200
    assert first.json() == PREFERENCES
    assert second.json() == {"rules": [PREFERENCES["rules"][1]]}
    assert (await client.get(url)).json() == second.json()


async def test_invalid_preferences_are_rejected(client: AsyncClient, session: AsyncSession) -> None:
    anna = await _user(session, "anna")
    await _login(client, anna)

    response = await client.put(
        f"/users/{anna.id}/channel-preferences", json={"rules": [{"min_severity": "info", "channels": []}]}
    )

    assert response.status_code == 422


async def test_only_the_user_or_an_admin_reads_and_writes(client: AsyncClient, session: AsyncSession) -> None:
    anna = await _user(session, "anna")
    bob = await _user(session, "bob")
    admin = await _user(session, "admin", GlobalRole.ADMIN)
    url = f"/users/{anna.id}/channel-preferences"

    await _login(client, bob)
    assert (await client.get(url)).status_code == 403
    assert (await client.put(url, json=PREFERENCES)).status_code == 403

    await _login(client, admin)
    assert (await client.put(url, json=PREFERENCES)).status_code == 200
    assert (await client.get(url)).json() == PREFERENCES


async def test_unauthenticated_requests_are_rejected(client: AsyncClient) -> None:
    url = f"/users/{uuid.uuid4()}/channel-preferences"

    assert (await client.get(url)).status_code == 401
    assert (await client.put(url, json=PREFERENCES)).status_code == 401


async def test_soft_deleted_or_missing_users_are_not_found(client: AsyncClient, session: AsyncSession) -> None:
    anna = await _user(session, "anna")
    admin = await _user(session, "admin", GlobalRole.ADMIN)
    await _login(client, admin)
    await client.delete(f"/users/{anna.id}")

    for user_id in (anna.id, uuid.uuid4()):
        url = f"/users/{user_id}/channel-preferences"
        assert (await client.get(url)).status_code == 404
        assert (await client.put(url, json=PREFERENCES)).status_code == 404
