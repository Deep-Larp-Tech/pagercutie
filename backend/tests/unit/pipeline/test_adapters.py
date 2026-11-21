import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from pagercutie.core.settings import Settings
from pagercutie.core.tokens import hash_token
from pagercutie.main import create_app
from pagercutie.pipeline.adapters import ADAPTERS, IngestState, bearer_token, ingest_state
from pagercutie.pipeline.ingest.stage import SourceCatalog
from pagercutie.sources.schemas import FixedSchema, SeverityMapping, SourceType
from pagercutie.sources.service import INGEST_PATHS, IngestSource

TOKEN = "secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def source(slug: str, source_type: SourceType, token: str = TOKEN) -> IngestSource:
    return IngestSource(
        id=uuid.uuid7(),
        slug=slug,
        type=source_type,
        team_id=uuid.uuid7(),
        schema_resolution=FixedSchema(mode="fixed", schema_id=uuid.uuid7()),
        severity=SeverityMapping(),
        token_hash=hash_token(token),
    )


def catalog(*sources: IngestSource) -> SourceCatalog:
    return SourceCatalog(sources={s.slug: s for s in sources})


CATALOG = catalog(source("hook", SourceType.WEBHOOK), source("socket", SourceType.WEBSOCKET))


@pytest.fixture
def app() -> FastAPI:
    # No lifespan runs (TestClient outside `with`), so no database or listener is needed.
    return create_app(Settings())


@pytest.fixture
def state(app: FastAPI) -> IngestState:
    state = ingest_state(app)
    state.catalog = CATALOG
    return state


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    yield TestClient(app)


def test_every_adapter_has_a_route_and_every_route_an_adapter() -> None:
    types = [adapter.type for adapter in ADAPTERS]

    assert sorted(types) == sorted(INGEST_PATHS)


@pytest.mark.parametrize(
    ("header", "token"),
    [("Bearer abc", "abc"), ("bearer  abc ", "abc"), ("Basic abc", None), ("Bearer", None), ("", None)],
)
def test_bearer_token(header: str, token: str | None) -> None:
    assert bearer_token({"authorization": header} if header else {}) == token


def test_webhook_before_the_catalog_loads_is_not_ready(client: TestClient) -> None:
    assert client.post("/ingest/hook", headers=AUTH, json={}).status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.parametrize(
    ("path", "headers", "expected"),
    [
        ("/ingest/missing", AUTH, status.HTTP_404_NOT_FOUND),
        # A WebSocket source cannot be fed through the webhook route.
        ("/ingest/socket", AUTH, status.HTTP_404_NOT_FOUND),
        ("/ingest/hook", {}, status.HTTP_401_UNAUTHORIZED),
        ("/ingest/hook", {"Authorization": "Bearer wrong"}, status.HTTP_401_UNAUTHORIZED),
        # Authenticated; rule loading is not implemented yet (ADR-0046).
        ("/ingest/hook", AUTH, status.HTTP_501_NOT_IMPLEMENTED),
    ],
)
def test_webhook_replies(
    client: TestClient, state: IngestState, path: str, headers: dict[str, str], expected: int
) -> None:
    assert client.post(path, headers=headers, json={}).status_code == expected


def test_dropped_catalog_makes_the_webhook_not_ready(client: TestClient, state: IngestState) -> None:
    state.drop_catalog()

    assert client.post("/ingest/hook", headers=AUTH, json={}).status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.parametrize(
    ("path", "headers", "expected"),
    [
        ("/ingest/missing/ws", AUTH, status.HTTP_404_NOT_FOUND),
        ("/ingest/hook/ws", AUTH, status.HTTP_404_NOT_FOUND),
        ("/ingest/socket/ws", {"Authorization": "Bearer wrong"}, status.HTTP_401_UNAUTHORIZED),
    ],
)
def test_websocket_handshake_is_denied_with_the_webhook_status(
    client: TestClient, state: IngestState, path: str, headers: dict[str, str], expected: int
) -> None:
    with pytest.raises(WebSocketDenialResponse) as denied, client.websocket_connect(path, headers=headers):
        pass

    assert denied.value.status_code == expected


def test_websocket_answers_each_frame(client: TestClient, state: IngestState) -> None:
    with client.websocket_connect("/ingest/socket/ws", headers=AUTH) as ws:
        ws.send_text("{}")
        assert ws.receive_json()["status"] == status.HTTP_501_NOT_IMPLEMENTED
        ws.send_bytes(b"{}")
        assert ws.receive_json()["status"] == status.HTTP_501_NOT_IMPLEMENTED


def test_rotated_token_closes_the_websocket(client: TestClient, state: IngestState) -> None:
    with client.websocket_connect("/ingest/socket/ws", headers=AUTH) as ws:
        state.catalog = catalog(source("socket", SourceType.WEBSOCKET, token="rotated"))
        ws.send_text("{}")
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()

    assert closed.value.code == status.WS_1008_POLICY_VIOLATION


def test_dropped_catalog_closes_the_websocket_with_try_again_later(client: TestClient, state: IngestState) -> None:
    with client.websocket_connect("/ingest/socket/ws", headers=AUTH) as ws:
        state.drop_catalog()
        ws.send_text("{}")
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()

    assert closed.value.code == status.WS_1013_TRY_AGAIN_LATER
