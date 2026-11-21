import uuid
from collections.abc import AsyncIterator, Callable, Iterator

import grpc
import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from pagercutie.core.errors import (
    Conflict,
    DomainError,
    Forbidden,
    NotFound,
    NotImplementedYet,
    NotReady,
    Unauthenticated,
)
from pagercutie.core.settings import Settings
from pagercutie.core.tokens import hash_token
from pagercutie.main import create_app
from pagercutie.pipeline.adapters import (
    ROUTE_ADAPTERS,
    SERVER_ADAPTERS,
    GrpcAdapter,
    IngestState,
    bearer_token,
    grpc_status,
    ingest_state,
)
from pagercutie.pipeline.evaluation.stage import RuleSet
from pagercutie.pipeline.ingest.stage import EventRejected, RejectReason, SourceCatalog
from pagercutie.sources.schemas import SeverityMapping, SourceType
from pagercutie.sources.service import INGEST_PATHS, IngestSource
from pagercutie.v1 import ingest_pb2

TOKEN = "secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def source(slug: str, source_type: SourceType, token: str = TOKEN) -> IngestSource:
    return IngestSource(
        id=uuid.uuid7(),
        slug=slug,
        type=source_type,
        team_id=uuid.uuid7(),
        severity=SeverityMapping(),
        token_hash=hash_token(token),
    )


def catalog(*sources: IngestSource) -> SourceCatalog:
    return SourceCatalog(sources={s.slug: s for s in sources})


CATALOG = catalog(
    source("hook", SourceType.WEBHOOK), source("socket", SourceType.WEBSOCKET), source("ledger", SourceType.PROTOBUF)
)
RULES = RuleSet(by_schema={}, any_schema=[])


@pytest.fixture
def app() -> FastAPI:
    # No lifespan runs (TestClient outside `with`), so no database or listener is needed.
    return create_app(Settings())


@pytest.fixture
def state(app: FastAPI) -> IngestState:
    state = ingest_state(app)
    state.catalog = CATALOG
    state.rule_set = RULES
    return state


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    yield TestClient(app)


def test_every_adapter_has_a_route_and_every_route_an_adapter() -> None:
    types = [adapter.type for adapter in (*ROUTE_ADAPTERS, *SERVER_ADAPTERS)]

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
    ],
)
def test_webhook_replies(
    client: TestClient, state: IngestState, path: str, headers: dict[str, str], expected: int
) -> None:
    assert client.post(path, headers=headers, json={}).status_code == expected


def test_webhook_before_the_rules_load_is_not_ready(client: TestClient, state: IngestState) -> None:
    state.rule_set = None

    assert client.post("/ingest/hook", headers=AUTH, json={}).status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_dropped_caches_make_the_webhook_not_ready(client: TestClient, state: IngestState) -> None:
    state.drop_caches()

    assert (state.catalog, state.rule_set) == (None, None)
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


def test_websocket_handshake_before_the_rules_load_is_not_ready(client: TestClient, state: IngestState) -> None:
    state.rule_set = None

    with pytest.raises(WebSocketDenialResponse) as denied, client.websocket_connect("/ingest/socket/ws", headers=AUTH):
        pass

    assert denied.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_websocket_answers_each_frame(client: TestClient, state: IngestState) -> None:
    # Without a window store the pipeline answers 501 in each reply frame, and the connection stays open.
    state.window_store = None
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


def drop_catalog(state: IngestState) -> None:
    state.catalog = None


def drop_rule_set(state: IngestState) -> None:
    state.rule_set = None


@pytest.mark.parametrize("drop", [drop_catalog, drop_rule_set])
def test_dropped_cache_closes_the_websocket_with_try_again_later(
    client: TestClient, state: IngestState, drop: Callable[[IngestState], None]
) -> None:
    with client.websocket_connect("/ingest/socket/ws", headers=AUTH) as ws:
        drop(state)
        ws.send_text("{}")
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()

    assert closed.value.code == status.WS_1013_TRY_AGAIN_LATER


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (NotFound("Source", uuid.uuid7()), grpc.StatusCode.NOT_FOUND),
        (Conflict("taken"), grpc.StatusCode.ALREADY_EXISTS),
        (Unauthenticated(), grpc.StatusCode.UNAUTHENTICATED),
        (Forbidden("no"), grpc.StatusCode.PERMISSION_DENIED),
        (NotImplementedYet("x"), grpc.StatusCode.UNIMPLEMENTED),
        (NotReady("x"), grpc.StatusCode.UNAVAILABLE),
        (EventRejected(RejectReason.UNDECODABLE, []), grpc.StatusCode.INVALID_ARGUMENT),
    ],
)
def test_grpc_status_of_domain_errors(error: DomainError, code: grpc.StatusCode) -> None:
    assert grpc_status(error) == code


type Send = grpc.aio.UnaryUnaryMultiCallable[ingest_pb2.Event, ingest_pb2.Accepted]


@pytest.fixture
async def grpc_send(state: IngestState) -> AsyncIterator[Send]:
    server, port = GrpcAdapter().server(state, "127.0.0.1:0")
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        yield channel.unary_unary(
            INGEST_PATHS[SourceType.PROTOBUF],
            request_serializer=ingest_pb2.Event.SerializeToString,
            response_deserializer=ingest_pb2.Accepted.FromString,
        )
    await server.stop(None)


async def grpc_code(send: Send, metadata: tuple[tuple[str, str], ...]) -> grpc.StatusCode:
    with pytest.raises(grpc.aio.AioRpcError) as failed:
        await send(ingest_pb2.Event(), metadata=metadata)
    return failed.value.code()


GRPC_AUTH = (("authorization", f"Bearer {TOKEN}"),)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ((*GRPC_AUTH, ("source-slug", "missing")), grpc.StatusCode.NOT_FOUND),
        # A webhook source cannot be fed through gRPC.
        ((*GRPC_AUTH, ("source-slug", "hook")), grpc.StatusCode.NOT_FOUND),
        (GRPC_AUTH, grpc.StatusCode.NOT_FOUND),
        ((("source-slug", "ledger"),), grpc.StatusCode.UNAUTHENTICATED),
        ((("authorization", "Bearer wrong"), ("source-slug", "ledger")), grpc.StatusCode.UNAUTHENTICATED),
        # Authenticated, but without a window store the pipeline is not complete.
        ((*GRPC_AUTH, ("source-slug", "ledger")), grpc.StatusCode.UNIMPLEMENTED),
    ],
)
async def test_grpc_replies(
    grpc_send: Send, state: IngestState, metadata: tuple[tuple[str, str], ...], expected: grpc.StatusCode
) -> None:
    state.window_store = None

    assert await grpc_code(grpc_send, metadata) == expected


@pytest.mark.anyio
@pytest.mark.parametrize("drop", [drop_catalog, drop_rule_set])
async def test_grpc_without_caches_is_unavailable(
    grpc_send: Send, state: IngestState, drop: Callable[[IngestState], None]
) -> None:
    drop(state)

    assert await grpc_code(grpc_send, (*GRPC_AUTH, ("source-slug", "ledger"))) == grpc.StatusCode.UNAVAILABLE
