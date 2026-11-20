import json
from typing import Any

import pytest
from httpx import AsyncClient

from conftest import ClientFactory
from pagercutie.core.errors import Conflict
from pagercutie.core.settings import Settings
from pagercutie.imports import service
from sse import parse_sse

pytestmark = pytest.mark.anyio

CSV = (
    b"first_name,last_name,skill_name,skill_difficulty,occurred_at,believability,description,location\n"
    b"Stas,Yurich,Vim,7,2026-01-01T09:00:00Z,9,Exited Vim,Office\n"
    b"Ada,Pupil,Feigning,2,2026-01-02T09:00:00Z,8,Nodded wisely,\n"
)
ROW = {
    "first_name": "Stas",
    "last_name": "Yurich",
    "skill_name": "Vim",
    "skill_difficulty": 7,
    "occurred_at": "2026-01-01T09:00:00Z",
    "believability": 9,
    "description": "Exited Vim",
}


async def import_file(client: AsyncClient, name: str, content: bytes, content_type: str | None = None) -> list[Any]:
    file = (name, content, content_type) if content_type else (name, content)
    response = await client.post("/imports/larp-events", files={"file": file})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


async def test_csv_import_streams_progress_then_completes(client: AsyncClient) -> None:
    events = await import_file(client, "events.csv", CSV, "text/csv")

    assert events == [
        {"type": "progress", "phase": "parsing", "processed": 0, "total": None},
        {"type": "progress", "phase": "validating", "processed": 0, "total": 2},
        {"type": "progress", "phase": "writing", "processed": 0, "total": 2},
        {"type": "progress", "phase": "writing", "processed": 2, "total": 2},
        {"type": "completed", "summary": {"persons_created": 2, "skills_created": 2, "events_created": 2}},
    ]
    assert len((await client.get("/larp-events")).json()) == 2


async def test_json_import_is_detected_by_content_type(client: AsyncClient) -> None:
    events = await import_file(client, "upload", json.dumps([ROW]).encode(), "application/json")

    assert events[-1]["summary"]["events_created"] == 1


async def test_invalid_row_fails_with_row_location(client: AsyncClient) -> None:
    content = json.dumps([ROW, {**ROW, "believability": 0}]).encode()

    events = await import_file(client, "events.json", content)

    assert [e["type"] for e in events] == ["progress", "failed"]
    assert events[-1]["status"] == 422
    assert [e["loc"] for e in events[-1]["detail"]] == [["body", "rows", 1, "believability"]]


async def test_domain_validation_failure_imports_nothing(client: AsyncClient) -> None:
    content = json.dumps([ROW, {**ROW, "occurred_at": "2999-01-01T00:00:00Z"}]).encode()

    events = await import_file(client, "events.json", content)

    assert events[-1]["type"] == "failed"
    assert [e["loc"] for e in events[-1]["detail"]] == [["body", "rows", 1, "occurred_at"]]
    assert (await client.get("/persons")).json() == []


async def test_failure_after_rows_were_written_rolls_everything_back(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    flush = service._flush
    flushes = 0

    async def flush_then_conflict(session: Any) -> None:
        nonlocal flushes
        flushes += 1
        if flushes == 2:
            raise Conflict("A concurrent change created the same person or skill, retry the import")
        await flush(session)

    monkeypatch.setattr(service, "BATCH_SIZE", 1)
    monkeypatch.setattr(service, "_flush", flush_then_conflict)

    events = await import_file(client, "events.csv", CSV, "text/csv")

    assert {"type": "progress", "phase": "writing", "processed": 1, "total": 2} in events
    assert events[-1] == {
        "type": "failed",
        "status": 409,
        "detail": "A concurrent change created the same person or skill, retry the import",
    }
    assert (await client.get("/persons")).json() == []


async def test_unexpected_error_still_ends_the_stream_with_failed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(*_: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_validate", crash)

    events = await import_file(client, "events.csv", CSV, "text/csv")

    assert events[-1] == {"type": "failed", "status": 500, "detail": "Import failed unexpectedly"}
    assert (await client.get("/persons")).json() == []


async def test_unsupported_file_type_is_415_before_streaming(client: AsyncClient) -> None:
    response = await client.post("/imports/larp-events", files={"file": ("events.txt", b"hello", "text/plain")})

    assert response.status_code == 415
    assert response.json() == {"detail": "Upload a .json or .csv file"}


async def test_too_large_file_is_413_before_streaming(make_client: ClientFactory, settings: Settings) -> None:
    async with make_client(settings.model_copy(update={"import_max_bytes": 64})) as client:
        response = await client.post("/imports/larp-events", files={"file": ("events.csv", CSV, "text/csv")})

    assert response.status_code == 413
    assert response.json() == {"detail": "File exceeds 64 bytes"}
