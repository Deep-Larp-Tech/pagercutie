"""Entrypoints of the ingest stage."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.errors import FieldError, InvalidInput, NotImplementedYet
from pagercutie.pipeline.messages import Event, RawEvent
from pagercutie.sources.schemas import SourceRead


class RejectReason(StrEnum):
    """Why ingest rejected an event; the `reason` label of `events_rejected_total` (SPEC §13)."""

    UNDECODABLE = "undecodable"
    SCHEMA_UNRESOLVED = "schema_unresolved"
    SCHEMA_INVALID = "schema_invalid"


class EventRejected(InvalidInput):
    """The event cannot be normalised; answered with `422` and the issues (SPEC §7)."""

    def __init__(self, reason: RejectReason, errors: list[FieldError]) -> None:
        super().__init__(errors)
        self.reason = reason


@dataclass(frozen=True)
class SourceCatalog:
    """Snapshot of the enabled sources and their compiled schemas, cached per replica (SPEC §7)."""

    # By slug.
    sources: Mapping[str, SourceRead]
    # Event schemas resolution may pick; the compiled validators are added with the implementation.
    schema_ids: frozenset[uuid.UUID]


async def load_catalog(session: AsyncSession) -> SourceCatalog:
    """Load the enabled sources and compile their schemas; rerun on `NOTIFY schemas_changed` (SPEC §5.3)."""
    raise NotImplementedYet("Source catalog")


def normalise(raw: RawEvent, catalog: SourceCatalog) -> Event:
    """Authenticate, decode, resolve and validate `raw` into an `Event`.

    Raises `NotFound` for an unknown or disabled source, `Unauthenticated` for a wrong token and `EventRejected`
    for input that cannot be decoded, resolved or validated.
    """
    raise NotImplementedYet("Event normalisation")
