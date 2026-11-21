"""Source adapters (SPEC §6, ADR-0057): each turns one transport into a `RawEvent` for the orchestrator.

Outside the stage packages because it calls `orchestrator.process_event`, which stages may not import. Adding a source
type means writing one adapter, adding it to `ADAPTERS` and its route to `sources.service.INGEST_PATHS`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Protocol

import structlog
from fastapi import APIRouter, Depends, FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.requests import HTTPConnection
from fastapi.responses import JSONResponse
from opentelemetry import metrics
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.errors import DomainError, NotImplementedYet, NotReady, error_body
from pagercutie.core.listen import OnChange
from pagercutie.pipeline import orchestrator
from pagercutie.pipeline.dedup.stage import WindowStore
from pagercutie.pipeline.evaluation.stage import RuleSet
from pagercutie.pipeline.ingest import stage as ingest
from pagercutie.pipeline.messages import IngestResult, RawEvent
from pagercutie.sources.schemas import SourceType
from pagercutie.sources.service import INGEST_PATHS

log = structlog.get_logger("ingest")

_meter = metrics.get_meter("pagercutie.ingest")
_ingested = _meter.create_counter("events_ingested_total", description="Events accepted with 202, by source")
_rejected = _meter.create_counter("events_rejected_total", description="Events answered with 422, by reason")

JSON = "application/json"


@dataclass
class IngestState:
    """What ingest reads on every event, one per replica (SPEC §5.2); a cache left `None` answers 503 or 501."""

    sessionmaker: async_sessionmaker[AsyncSession]
    # None before the first load and after the listening connection is lost (ADR-0059).
    catalog: ingest.SourceCatalog | None = None
    # None until rule loading and the Redis window store are implemented (ADR-0057).
    rule_set: RuleSet | None = None
    window_store: WindowStore | None = None

    def drop_catalog(self) -> None:
        """Fail closed: ingest answers 503 until the next reload instead of trusting a catalog that may be stale."""
        self.catalog = None


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


def _rule_set(state: IngestState) -> RuleSet:
    if state.rule_set is None:
        raise NotImplementedYet("Rule set loading")
    return state.rule_set


def _window_store(state: IngestState) -> WindowStore:
    if state.window_store is None:
        raise NotImplementedYet("Redis window store")
    return state.window_store


def catalog_reloader(state: IngestState) -> OnChange:
    """Reloads `state.catalog`; run on (re)connect and on `NOTIFY sources_changed` (ADR-0058)."""

    async def reload() -> None:
        async with state.sessionmaker() as session:
            catalog = await ingest.load_catalog(session)
        # One assignment, so a request never sees a half-built catalog.
        state.catalog = catalog
        log.info("ingest.catalog_loaded", message="Source catalog reloaded", sources=len(catalog.sources))

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


async def process(state: IngestState, raw: RawEvent, catalog: ingest.SourceCatalog) -> IngestResult:
    """Runs `raw` through the pipeline and counts the outcome (SPEC §13)."""
    try:
        result = await orchestrator.process_event(
            raw, state.sessionmaker, catalog, _rule_set(state), _window_store(state)
        )
    except ingest.EventRejected as e:
        _rejected.add(1, {"reason": e.reason})
        raise
    _ingested.add(1, {"source": raw.source_slug})
    return result


def error_response(error: DomainError) -> JSONResponse:
    status_code, detail = error_body(error)
    return JSONResponse({"detail": detail}, status_code=status_code)


class SourceAdapter(Protocol):
    """Receives raw input for one source type and hands it to the orchestrator."""

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
            raw = RawEvent(
                source_slug=source_slug,
                source_type=source_type,
                token=token,
                content_type=request.headers.get("content-type", JSON),
                body=await request.body(),
            )
            return await process(state, raw, catalog)

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
                        result = await process(state, raw, catalog)
                    except DomainError as e:
                        status_code, detail = error_body(e)
                        await websocket.send_json({"status": status_code, "detail": detail})
                    else:
                        await websocket.send_text(result.model_dump_json())
            except WebSocketDisconnect:
                return

        return router


ADAPTERS: tuple[SourceAdapter, ...] = (WebhookAdapter(), WebSocketAdapter())
