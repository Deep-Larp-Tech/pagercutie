"""What ingest reads on every event, one per replica, and the handlers that reload it (SPEC §5.2, §5.3).

Outside the stage packages because it holds several stages' caches; the stages' own loaders do the work.
"""

from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI
from fastapi.requests import HTTPConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.errors import NotReady
from pagercutie.core.listen import OnChange
from pagercutie.pipeline.dedup.stage import WindowStore
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.pipeline.ingest import stage as ingest

log = structlog.get_logger("ingest")


@dataclass
class IngestState:
    """The replica's ingest caches and window store; a cache left `None` answers 503."""

    sessionmaker: async_sessionmaker[AsyncSession]
    window_store: WindowStore
    schemas: ingest.SchemaCache
    # None before the first load and after the listening connection is lost (ADR-0063, ADR-0093).
    catalog: ingest.SourceCatalog | None = None
    rule_set: evaluation.RuleSet | None = None

    def drop_caches(self) -> None:
        """Fail closed: ingest answers 503 until the next reload instead of trusting caches that may be stale."""
        self.catalog = None
        self.rule_set = None
        self.schemas.invalidate()


def ingest_state(app: FastAPI) -> IngestState:
    """The replica's `IngestState`, set by `create_app`."""
    state = app.state.ingest
    if not isinstance(state, IngestState):
        raise TypeError("app.state.ingest is not an IngestState; create the app with create_app")
    return state


def get_ingest_state(connection: HTTPConnection) -> IngestState:
    return ingest_state(connection.app)


IngestStateDep = Annotated[IngestState, Depends(get_ingest_state)]


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


def schema_invalidator(state: IngestState) -> OnChange:
    """Drops the cached team schemas; run on (re)connect and on `NOTIFY schemas_changed` (ADR-0100)."""

    async def invalidate() -> None:
        state.schemas.invalidate()
        log.info("ingest.schemas_invalidated", message="Team schemas will be reloaded")

    return invalidate
