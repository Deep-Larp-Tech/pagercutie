import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def create_person_and_skill(client: AsyncClient) -> tuple[str, str]:
    person = await client.post("/persons", json={"first_name": "Stas", "last_name": "Yurich"})
    skill = await client.post("/skills", json={"name": "Vim", "difficulty": 2})
    return person.json()["id"], skill.json()["id"]


def event_payload(person_id: str, skill_id: str, occurred_at: str = "2026-01-01T09:00:00Z") -> dict[str, object]:
    return {
        "person_id": person_id,
        "skill_id": skill_id,
        "occurred_at": occurred_at,
        "believability": 10,
        "description": "Exited Vim on the first try",
        "location": "Office",
    }


async def test_create_event_returns_nested_person_and_skill(client: AsyncClient) -> None:
    person_id, skill_id = await create_person_and_skill(client)

    response = await client.post("/larp-events", json=event_payload(person_id, skill_id))

    assert response.status_code == 201
    body = response.json()
    assert body["elo_delta"] == 16
    assert body["person"]["larp_elo"] == 1016
    assert body["skill"] == {"id": skill_id, "name": "Vim", "difficulty": 2}


async def test_future_event_is_422_in_fastapi_error_shape(client: AsyncClient) -> None:
    person_id, skill_id = await create_person_and_skill(client)

    response = await client.post("/larp-events", json=event_payload(person_id, skill_id, "2999-01-01T00:00:00Z"))

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"loc": ["body", "occurred_at"], "msg": "must not be in the future", "type": "value_error"}
    ]


async def test_unknown_person_is_404(client: AsyncClient) -> None:
    _, skill_id = await create_person_and_skill(client)

    response = await client.post("/larp-events", json=event_payload(str(uuid.uuid7()), skill_id))

    assert response.status_code == 404
