"""Source adapters (SPEC §6, ADR-0061, ADR-0101): each authenticates its source once and turns one transport into
a `RawEvent` for the orchestrator.

Outside the stage packages because it calls `orchestrator.process_event`, which stages may not import. Adding a source
type means writing one adapter, adding it to `ADAPTERS` and its route to `sources.service.INGEST_PATHS`.
"""

from collections.abc import Mapping
from typing import Protocol

import structlog
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from opentelemetry import metrics

from pagercutie.core.errors import DomainError, NotReady, error_body
from pagercutie.pipeline import orchestrator
from pagercutie.pipeline.admission import INGEST_ADMISSION, INGEST_RESPONSES, admission_of
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.pipeline.ingest import stage as ingest
from pagercutie.pipeline.messages import IngestResult, RawEvent
from pagercutie.pipeline.state import IngestState, IngestStateDep, current_catalog, current_rule_set, ingest_state
from pagercutie.sources.schemas import SourceType
from pagercutie.sources.service import INGEST_PATHS

log = structlog.get_logger("ingest")

_meter = metrics.get_meter("pagercutie.ingest")
_ingested = _meter.create_counter("events_ingested_total", description="Events accepted with 202, by source")
_rejected = _meter.create_counter("events_rejected_total", description="Events answered with 422, by reason")


def ingest_router() -> APIRouter:
    """The router every adapter declares its route on; dependencies shared by all ingest routes go here."""
    return APIRouter(tags=["ingest"])


def bearer_token(headers: Mapping[str, str]) -> str | None:
    """The token of an `Authorization: Bearer <token>` header."""
    scheme, _, token = headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


async def process(state: IngestState, raw: RawEvent, rule_set: evaluation.RuleSet) -> IngestResult:
    """Runs `raw` through the pipeline and counts the outcome (SPEC §13)."""
    try:
        result = await orchestrator.process_event(
            raw, state.sessionmaker, state.schemas.load, rule_set, state.window_store
        )
    except ingest.EventRejected as e:
        _rejected.add(1, {"reason": e.reason})
        raise
    _ingested.add(1, {"source": raw.source.slug})
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
        router = ingest_router()
        source_type = self.type

        # Producers are not clients of the management API (DOMAIN §7); keeps it out of the generated client.
        @router.post(
            INGEST_PATHS[source_type],
            status_code=status.HTTP_202_ACCEPTED,
            include_in_schema=False,
            dependencies=[INGEST_ADMISSION],
            responses=INGEST_RESPONSES,
        )
        async def ingest_webhook(source_slug: str, request: Request, state: IngestStateDep) -> IngestResult:
            """Answers once every resulting alert and delivery is committed (SPEC §5.1); `422` for invalid input."""
            # Before reading the body, so an unauthenticated producer costs no more than a lookup.
            token = bearer_token(request.headers)
            source = ingest.authenticate(current_catalog(state), source_slug, source_type, token)
            rule_set = current_rule_set(state)
            return await process(state, RawEvent(source=source, body=await request.body()), rule_set)

        return router


class WebSocketAdapter:
    """`/ingest/{source_slug}/ws`: one JSON event per frame, answered in order once committed."""

    @property
    def type(self) -> SourceType:
        return SourceType.WEBSOCKET

    def router(self) -> APIRouter:
        router = ingest_router()
        source_type = self.type

        @router.websocket(INGEST_PATHS[source_type])
        async def ingest_websocket(websocket: WebSocket, source_slug: str) -> None:
            state = ingest_state(websocket.app)
            token = bearer_token(websocket.headers)
            try:
                catalog = current_catalog(state)
                source = ingest.authenticate(catalog, source_slug, source_type, token)
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
                    # A reload swaps the whole catalog, so the source is checked again only after one: a dropped
                    # catalog, a rotated token or a disabled source ends the connection.
                    try:
                        if (latest := current_catalog(state)) is not catalog:
                            source = ingest.authenticate(latest, source_slug, source_type, token)
                            catalog = latest
                        rule_set = current_rule_set(state)
                    except NotReady as e:
                        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason=str(e))
                        return
                    except DomainError as e:
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))
                        return
                    try:
                        # Per frame: a refused frame gets a 429 or 503 error frame and the connection stays open.
                        async with admission_of(websocket.app).admit(
                            source_slug, websocket.headers.get("authorization")
                        ):
                            result = await process(state, RawEvent(source=source, body=body), rule_set)
                    except DomainError as e:
                        status_code, detail = error_body(e)
                        await websocket.send_json({"status": status_code, "detail": detail})
                    else:
                        await websocket.send_text(result.model_dump_json())
            except WebSocketDisconnect:
                return

        return router


ADAPTERS: tuple[SourceAdapter, ...] = (WebhookAdapter(), WebSocketAdapter())
