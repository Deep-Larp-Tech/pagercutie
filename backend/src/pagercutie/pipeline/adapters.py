"""Source adapters (SPEC §6, ADR-0046): each turns one transport into a `RawEvent` for the orchestrator.

Outside the stage packages because it calls `orchestrator.process_event`, which stages may not import. Adding a source
type means writing one adapter, adding it to `ADAPTERS` and to `sources.service.INGESTIBLE_TYPES`.
"""

from collections.abc import Mapping
from typing import Annotated, Protocol

import structlog
from fastapi import APIRouter, Depends, FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.requests import HTTPConnection
from fastapi.responses import JSONResponse
from opentelemetry import metrics
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.errors import DomainError, NotImplementedYet, Unavailable, error_body
from pagercutie.core.listen import OnChange
from pagercutie.core.schemas import error_responses
from pagercutie.pipeline import orchestrator
from pagercutie.pipeline.dedup.stage import WindowStore
from pagercutie.pipeline.evaluation.stage import RuleSet
from pagercutie.pipeline.ingest import stage as ingest
from pagercutie.pipeline.messages import IngestResult, RawEvent
from pagercutie.sources.schemas import SourceType

log = structlog.get_logger("ingest")

_meter = metrics.get_meter("pagercutie.ingest")
_ingested = _meter.create_counter("events_ingested_total", description="Events accepted with 202, by source")
_rejected = _meter.create_counter("events_rejected_total", description="Events answered with 422, by reason")

JSON = "application/json"


def current_catalog(app: FastAPI) -> ingest.SourceCatalog:
    """The replica's source catalog; `Unavailable` (503) until the first load."""
    catalog: ingest.SourceCatalog | None = app.state.source_catalog
    if catalog is None:
        raise Unavailable("Sources are not loaded yet")
    return catalog


def _rule_set(app: FastAPI) -> RuleSet:
    rules: RuleSet | None = app.state.rule_set
    if rules is None:
        raise NotImplementedYet("Rule set loading")
    return rules


def _window_store(app: FastAPI) -> WindowStore:
    windows: WindowStore | None = app.state.window_store
    if windows is None:
        raise NotImplementedYet("Redis window store")
    return windows


def catalog_reloader(app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]) -> OnChange:
    """Reloads `app.state.source_catalog`; run on start and on `NOTIFY sources_changed` (ADR-0047)."""

    async def reload() -> None:
        async with sessionmaker() as session:
            catalog = await ingest.load_catalog(session)
        # One assignment, so a request never sees a half-built catalog.
        app.state.source_catalog = catalog
        log.info("ingest.catalog_loaded", message="Source catalog reloaded", sources=len(catalog.sources))

    return reload


def get_catalog(connection: HTTPConnection) -> ingest.SourceCatalog:
    return current_catalog(connection.app)


CatalogDep = Annotated[ingest.SourceCatalog, Depends(get_catalog)]


def bearer_token(headers: Mapping[str, str]) -> str | None:
    """The token of an `Authorization: Bearer <token>` header."""
    scheme, _, token = headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


async def process(app: FastAPI, raw: RawEvent, catalog: ingest.SourceCatalog) -> IngestResult:
    """Runs `raw` through the pipeline and counts the outcome (SPEC §13)."""
    try:
        result = await orchestrator.process_event(
            raw, app.state.sessionmaker, catalog, _rule_set(app), _window_store(app)
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

        @router.post(
            "/ingest/{source_slug}",
            status_code=status.HTTP_202_ACCEPTED,
            responses=error_responses(401, 404, 501, 503),
            # Producers are not clients of the management API (DOMAIN §7); keeps it out of the generated client.
            include_in_schema=False,
        )
        async def ingest_webhook(source_slug: str, request: Request, catalog: CatalogDep) -> IngestResult:
            """Answers once every resulting alert and delivery is committed (SPEC §5.1); `422` for invalid input."""
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
            return await process(request.app, raw, catalog)

        return router


class WebSocketAdapter:
    """`/ingest/{source_slug}/ws`: one JSON event per frame, answered in order once committed."""

    @property
    def type(self) -> SourceType:
        return SourceType.WEBSOCKET

    def router(self) -> APIRouter:
        router = APIRouter(tags=["ingest"])
        source_type = self.type

        @router.websocket("/ingest/{source_slug}/ws")
        async def ingest_websocket(websocket: WebSocket, source_slug: str) -> None:
            app = websocket.app
            token = bearer_token(websocket.headers)
            try:
                ingest.authenticate(current_catalog(app), source_slug, source_type, token)
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
                    catalog = current_catalog(app)
                    try:
                        # Per frame, so a rotated token or a disabled source ends the connection.
                        ingest.authenticate(catalog, source_slug, source_type, token)
                    except DomainError as e:
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))
                        return
                    raw = RawEvent(
                        source_slug=source_slug, source_type=source_type, token=token, content_type=JSON, body=body
                    )
                    try:
                        result = await process(app, raw, catalog)
                    except DomainError as e:
                        status_code, detail = error_body(e)
                        await websocket.send_json({"status": status_code, "detail": detail})
                    else:
                        await websocket.send_text(result.model_dump_json())
            except WebSocketDisconnect:
                return

        return router


ADAPTERS: tuple[SourceAdapter, ...] = (WebhookAdapter(), WebSocketAdapter())
