import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio

STAS = {"first_name": "Stas", "last_name": "Yurich"}


async def test_create_returns_exactly_the_read_dto(client: AsyncClient) -> None:
    response = await client.post("/persons", json=STAS)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "first_name", "last_name", "larp_elo"}  # no model internals leak
    assert body["larp_elo"] == 1000


async def test_duplicate_person_is_409(client: AsyncClient) -> None:
    await client.post("/persons", json=STAS)

    response = await client.post("/persons", json=STAS)

    assert response.status_code == 409
    assert response.json() == {"detail": "A person with this first and last name already exists"}


@pytest.mark.parametrize(
    "payload",
    [
        {**STAS, "id": str(uuid.uuid7())},  # unknown/extra fields are rejected
        {**STAS, "first_name": ""},
        {**STAS, "first_name": "nul\x00byte"},
        {**STAS, "larp_elo": -1},
    ],
)
async def test_invalid_payload_is_422(client: AsyncClient, payload: dict[str, object]) -> None:
    response = await client.post("/persons", json=payload)

    assert response.status_code == 422


async def test_update_then_delete(client: AsyncClient) -> None:
    person = (await client.post("/persons", json=STAS)).json()

    updated = await client.patch(f"/persons/{person['id']}", json={"first_name": "Stanislav"})
    deleted = await client.delete(f"/persons/{person['id']}")
    missing = await client.get(f"/persons/{person['id']}")

    assert updated.json()["first_name"] == "Stanislav"
    assert deleted.status_code == 204
    assert missing.status_code == 404
