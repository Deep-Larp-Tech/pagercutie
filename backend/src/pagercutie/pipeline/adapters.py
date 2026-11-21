"""Source adapters (SPEC §6, ADR-0061, ADR-0099): each turns one transport into a `RawEvent` for the orchestrator.

Outside the stage packages because it calls `orchestrator.process_event`, which stages may not import. Adding a source
type means writing one adapter, adding it to `ROUTE_ADAPTERS` or `SERVER_ADAPTERS` and its route to
`sources.service.INGEST_PATHS`.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Protocol

import grpc
import structlog
from fastapi import APIRouter, Depends, FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.requests import HTTPConnection
from fastapi.responses import JSONResponse
from grpc_reflection.v1alpha import reflection
from opentelemetry import metrics
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.errors import (
    Conflict,
    DomainError,
    Forbidden,
    InvalidInput,
    NotFound,
    NotImplementedYet,
    NotReady,
    Unauthenticated,
    error_body,
)
from pagercutie.core.listen import OnChange
from pagercutie.core.settings import Settings
from pagercutie.core.workers import Worker
from pagercutie.pipeline import orchestrator
from pagercutie.pipeline.dedup.stage import WindowStore
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.pipeline.ingest import stage as ingest
from pagercutie.pipeline.messages import IngestResult, RawEvent
from pagercutie.sources.schemas import SourceType
from pagercutie.sources.service import GRPC_INGEST_SERVICE, INGEST_PATHS
from pagercutie.v1 import ingest_pb2

log = structlog.get_logger("ingest")

_meter = metrics.get_meter("pagercutie.ingest")
_ingested = _meter.create_counter("events_ingested_total", description="Events accepted with 202, by source")
_rejected = _meter.create_counter("events_rejected_total", description="Events answered with 422, by reason")

JSON = "application/json"
GRPC_PROTO = "application/grpc+proto"


@dataclass
class IngestState:
    """What ingest reads on every event, one per replica (SPEC §5.2); a cache left `None` answers 503 or 501."""

    sessionmaker: async_sessionmaker[AsyncSession]
    # The caches are None before the first load and after the listening connection is lost (ADR-0063, ADR-0093).
    catalog: ingest.SourceCatalog | None = None
    rule_set: evaluation.RuleSet | None = None
    # Set by `create_app` to the replica's `RedisWindowStore`; None answers 501.
    window_store: WindowStore | None = None

    def drop_caches(self) -> None:
        """Fail closed: ingest answers 503 until the next reload instead of trusting caches that may be stale."""
        self.catalog = None
        self.rule_set = None


def ingest_state(app: FastAPI) -> IngestState:
    """The replica's `IngestState`, set by `create_app`."""
    state = app.state.ingest
    if not isinstance(state, IngestState):
        raise TypeError("app.state.ingest is not an IngestState; create the app with create_app")
    return state


def current_catalog(state: IngestState) -> ingest.SourceCatalog:
    """The replica's source catalog; `NotReady` (503) while it is not loaded."""
    if state.catalog is None:
        raise NotReady("Sources are not loaded")
    return state.catalog


def current_rule_set(state: IngestState) -> evaluation.RuleSet:
    """The replica's compiled rules; `NotReady` (503) while they are not loaded."""
    if state.rule_set is None:
        raise NotReady("Rules are not loaded")
    return state.rule_set


def _window_store(state: IngestState) -> WindowStore:
    if state.window_store is None:
        raise NotImplementedYet("Redis window store")
    return state.window_store


def catalog_reloader(state: IngestState) -> OnChange:
    """Reloads `state.catalog`; run on (re)connect and on `NOTIFY sources_changed` (ADR-0062)."""

    async def reload() -> None:
        async with state.sessionmaker() as session:
            catalog = await ingest.load_catalog(session)
        # One assignment, so a request never sees a half-built catalog.
        state.catalog = catalog
        log.info("ingest.catalog_loaded", message="Source catalog reloaded", sources=len(catalog.sources))

    return reload


def rule_set_reloader(state: IngestState) -> OnChange:
    """Reloads `state.rule_set`; run on (re)connect and on `NOTIFY rules_changed` or `access_changed` (SPEC §5.3)."""

    async def reload() -> None:
        async with state.sessionmaker() as session:
            rule_set = await evaluation.load_rule_set(session)
        state.rule_set = rule_set
        log.info("ingest.rules_loaded", message="Rule set reloaded")

    return reload


def get_ingest_state(connection: HTTPConnection) -> IngestState:
    return ingest_state(connection.app)


IngestStateDep = Annotated[IngestState, Depends(get_ingest_state)]


def bearer_token(headers: Mapping[str, str]) -> str | None:
    """The token of an `Authorization: Bearer <token>` header."""
    scheme, _, token = headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


async def process(
    state: IngestState, raw: RawEvent, catalog: ingest.SourceCatalog, rule_set: evaluation.RuleSet
) -> IngestResult:
    """Runs `raw` through the pipeline and counts the outcome (SPEC §13)."""
    try:
        result = await orchestrator.process_event(raw, state.sessionmaker, catalog, rule_set, _window_store(state))
    except ingest.EventRejected as e:
        _rejected.add(1, {"reason": e.reason})
        raise
    _ingested.add(1, {"source": raw.source_slug})
    return result


def error_response(error: DomainError) -> JSONResponse:
    status_code, detail = error_body(error)
    return JSONResponse({"detail": detail}, status_code=status_code)


class RouteAdapter(Protocol):
    """Receives raw input for one source type on routes of the FastAPI app and hands it to the orchestrator."""

    @property
    def type(self) -> SourceType: ...

    def router(self) -> APIRouter: ...


class WebhookAdapter:
    """`POST /ingest/{source_slug}`: one JSON event per request body."""

    @property
    def type(self) -> SourceType:
        return SourceType.WEBHOOK

    def router(self) -> APIRouter:
        router = APIRouter(tags=["ingest"])
        source_type = self.type

        # Producers are not clients of the management API (DOMAIN §7); keeps it out of the generated client.
        @router.post(INGEST_PATHS[source_type], status_code=status.HTTP_202_ACCEPTED, include_in_schema=False)
        async def ingest_webhook(source_slug: str, request: Request, state: IngestStateDep) -> IngestResult:
            """Answers once every resulting alert and delivery is committed (SPEC §5.1); `422` for invalid input."""
            catalog = current_catalog(state)
            token = bearer_token(request.headers)
            # Before reading the body, so an unauthenticated producer costs no more than a lookup.
            ingest.authenticate(catalog, source_slug, source_type, token)
            rule_set = current_rule_set(state)
            raw = RawEvent(
                source_slug=source_slug,
                source_type=source_type,
                token=token,
                content_type=request.headers.get("content-type", JSON),
                body=await request.body(),
            )
            return await process(state, raw, catalog, rule_set)

        return router


class WebSocketAdapter:
    """`/ingest/{source_slug}/ws`: one JSON event per frame, answered in order once committed."""

    @property
    def type(self) -> SourceType:
        return SourceType.WEBSOCKET

    def router(self) -> APIRouter:
        router = APIRouter(tags=["ingest"])
        source_type = self.type

        @router.websocket(INGEST_PATHS[source_type])
        async def ingest_websocket(websocket: WebSocket, source_slug: str) -> None:
            state = ingest_state(websocket.app)
            token = bearer_token(websocket.headers)
            try:
                ingest.authenticate(current_catalog(state), source_slug, source_type, token)
                current_rule_set(state)
            except DomainError as e:
                # The handshake fails with the status the webhook would answer.
                await websocket.send_denial_response(error_response(e))
                return
            await websocket.accept()
            try:
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    data = message.get("bytes")
                    body = data if isinstance(data, bytes) else str(message.get("text") or "").encode()
                    # Per frame, so a dropped catalog, a rotated token or a disabled source ends the connection.
                    try:
                        catalog = current_catalog(state)
                        ingest.authenticate(catalog, source_slug, source_type, token)
                        rule_set = current_rule_set(state)
                    except NotReady as e:
                        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason=str(e))
                        return
                    except DomainError as e:
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))
                        return
                    raw = RawEvent(
                        source_slug=source_slug, source_type=source_type, token=token, content_type=JSON, body=body
                    )
                    try:
                        result = await process(state, raw, catalog, rule_set)
                    except DomainError as e:
                        status_code, detail = error_body(e)
                        await websocket.send_json({"status": status_code, "detail": detail})
                    else:
                        await websocket.send_text(result.model_dump_json())
            except WebSocketDisconnect:
                return

        return router


class ServerAdapter(Protocol):
    """Receives raw input for one source type on a server of its own, run as a worker beside the FastAPI app."""

    @property
    def type(self) -> SourceType: ...

    def worker(self, state: IngestState, settings: Settings) -> Worker: ...


# Largest event body the gRPC server accepts; the same limit Caddy puts on webhook bodies.
MAX_GRPC_MESSAGE_BYTES = 1024 * 1024
# Seconds in-flight calls get to finish when the replica stops.
GRPC_STOP_GRACE_S = 5.0


def grpc_status(error: DomainError) -> grpc.StatusCode:
    """The gRPC status for a domain error; the counterpart of `error_body` for the gRPC adapter."""
    match error:
        case NotFound():
            return grpc.StatusCode.NOT_FOUND
        case Conflict():
            return grpc.StatusCode.ALREADY_EXISTS
        case Unauthenticated():
            return grpc.StatusCode.UNAUTHENTICATED
        case Forbidden():
            return grpc.StatusCode.PERMISSION_DENIED
        case NotImplementedYet():
            return grpc.StatusCode.UNIMPLEMENTED
        case NotReady():
            return grpc.StatusCode.UNAVAILABLE
        case InvalidInput():
            return grpc.StatusCode.INVALID_ARGUMENT
    raise TypeError(f"Unhandled domain error {type(error).__name__}")


def text_metadata(context: grpc.aio.ServicerContext[bytes, ingest_pb2.Accepted]) -> dict[str, str]:
    """The call's metadata with text values; gRPC lowercases keys, and `-bin` keys carry bytes."""
    return {key: value for key, value in context.invocation_metadata() or () if isinstance(value, str)}


class GrpcAdapter:
    """`pagercutie.v1.IngestService/Send`: one serialised `Event` per unary call (ADR-0099).

    The source is named by the `source-slug` metadata entry, since a gRPC method path carries no parameters.
    """

    @property
    def type(self) -> SourceType:
        return SourceType.PROTOBUF

    def handler(self, state: IngestState) -> grpc.GenericRpcHandler:
        source_type = self.type

        async def send(
            body: bytes, context: grpc.aio.ServicerContext[bytes, ingest_pb2.Accepted]
        ) -> ingest_pb2.Accepted:
            """Answers once every resulting alert and delivery is committed (SPEC §5.1)."""
            metadata = text_metadata(context)
            slug = metadata.get("source-slug", "")
            token = bearer_token(metadata)
            try:
                catalog = current_catalog(state)
                ingest.authenticate(catalog, slug, source_type, token)
                rule_set = current_rule_set(state)
                raw = RawEvent(
                    source_slug=slug, source_type=source_type, token=token, content_type=GRPC_PROTO, body=body
                )
                result = await process(state, raw, catalog, rule_set)
            except DomainError as e:
                await context.abort(grpc_status(e), str(e))
            return ingest_pb2.Accepted(event_id=str(result.event_id), matches=result.matches)

        # No request deserializer: the handler gets the raw bytes, and `ingest.normalise` decodes them once.
        return grpc.method_handlers_generic_handler(
            GRPC_INGEST_SERVICE,
            {
                "Send": grpc.unary_unary_rpc_method_handler(
                    send, response_serializer=ingest_pb2.Accepted.SerializeToString
                )
            },
        )

    def server(self, state: IngestState, address: str) -> tuple[grpc.aio.Server, int]:
        """A gRPC server for the ingest service bound to `address`, not started, and the port it bound."""
        server = grpc.aio.server(options=[("grpc.max_receive_message_length", MAX_GRPC_MESSAGE_BYTES)])
        server.add_generic_rpc_handlers([self.handler(state)])
        # Lets producers call the service with grpcurl without a copy of the .proto file.
        reflection.enable_server_reflection([GRPC_INGEST_SERVICE, reflection.SERVICE_NAME], server)
        return server, server.add_insecure_port(address)

    def worker(self, state: IngestState, settings: Settings) -> Worker:
        async def run(stopping: asyncio.Event) -> None:
            server, port = self.server(state, f"[::]:{settings.grpc_port}")
            await server.start()
            log.info("ingest.grpc_listening", message="gRPC ingest listening", port=port)
            try:
                await stopping.wait()
            finally:
                await server.stop(GRPC_STOP_GRACE_S)

        return Worker(name="grpc-ingest", run=run)


ROUTE_ADAPTERS: tuple[RouteAdapter, ...] = (WebhookAdapter(), WebSocketAdapter())
SERVER_ADAPTERS: tuple[ServerAdapter, ...] = (GrpcAdapter(),)
