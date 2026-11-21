"""Entrypoints of the ingest stage."""

import hmac
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import assert_never

import orjson
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.enums import Severity
from pagercutie.core.errors import FieldError, InvalidInput, SourceSlugNotFound, Unauthenticated
from pagercutie.core.payload import field_value
from pagercutie.core.tokens import hash_token
from pagercutie.pipeline.messages import Event, RawEvent
from pagercutie.sources.schemas import DiscriminatedSchema, FixedSchema, SchemaResolution, SeverityMapping, SourceType
from pagercutie.sources.service import IngestSource, load_ingest_sources


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
    """Snapshot of the enabled sources that have an ingest token, cached per replica (SPEC §6, ADR-0058)."""

    # By slug. `IngestSource`, not `SourceRead`: it carries the token hash.
    sources: Mapping[str, IngestSource]


async def load_catalog(session: AsyncSession) -> SourceCatalog:
    """Load the enabled sources that have an ingest token; rerun on `NOTIFY sources_changed` (SPEC §5.3)."""
    return SourceCatalog(sources={source.slug: source for source in await load_ingest_sources(session)})


def authenticate(catalog: SourceCatalog, slug: str, source_type: SourceType, token: str | None) -> IngestSource:
    """The source behind `slug` if it is enabled, has this adapter's type, and `token` is its current token.

    Raises `SourceSlugNotFound` (404) or `Unauthenticated` (401).
    """
    source = catalog.sources.get(slug)
    if source is None or source.type != source_type:
        raise SourceSlugNotFound(slug)
    if token is None or not hmac.compare_digest(hash_token(token), source.token_hash):
        raise Unauthenticated()
    return source


def as_key(value: JsonValue) -> str:
    """A payload value as a mapping key: strings as they are, anything else as its JSON text (`2`, `true`)."""
    return value if isinstance(value, str) else orjson.dumps(value).decode()


def decode(body: bytes) -> dict[str, JsonValue]:
    """The body as a JSON object. Every adapter delivers JSON today; `RawEvent.content_type` selects the decoder
    once a non-JSON source type (protobuf) exists."""
    try:
        payload: JsonValue = orjson.loads(body)
    except orjson.JSONDecodeError as e:
        raise EventRejected(RejectReason.UNDECODABLE, [FieldError((), f"not valid JSON: {e}")]) from e
    if not isinstance(payload, dict):
        raise EventRejected(RejectReason.UNDECODABLE, [FieldError((), "must be a JSON object")])
    return payload


def resolve_schema(resolution: SchemaResolution, payload: Mapping[str, JsonValue]) -> uuid.UUID:
    """The event's schema ID (SPEC §7)."""
    match resolution:
        case FixedSchema(schema_id=schema_id):
            return schema_id
        case DiscriminatedSchema(field=field, mapping=mapping):
            value = field_value(payload, field)
            if value is None:
                raise EventRejected(RejectReason.SCHEMA_UNRESOLVED, [FieldError((field,), "is missing")])
            key = as_key(value)
            if (schema_id := mapping.get(key)) is None:
                raise EventRejected(
                    RejectReason.SCHEMA_UNRESOLVED, [FieldError((field,), f"no schema for value {key}")]
                )
            return schema_id
        case _:
            assert_never(resolution)


def map_severity(mapping: SeverityMapping, payload: Mapping[str, JsonValue]) -> Severity:
    """The normalised severity; `mapping.default` when the field is unset, missing or has an unmapped value."""
    if mapping.field is None:
        return mapping.default
    value = field_value(payload, mapping.field)
    if value is None:
        return mapping.default
    return mapping.values.get(as_key(value), mapping.default)


def normalise(raw: RawEvent, catalog: SourceCatalog) -> Event:
    """Authenticate, decode, resolve and validate `raw` into an `Event`.

    Raises `SourceSlugNotFound` for an unknown, disabled or tokenless source or one of another type, `Unauthenticated`
    for a missing or wrong token and `EventRejected` for input that cannot be decoded, resolved or validated. JSON
    Schema validation (`SCHEMA_INVALID`) is added with the event schema cache.
    """
    source = authenticate(catalog, raw.source_slug, raw.source_type, raw.token)
    payload = decode(raw.body)
    return Event(
        event_id=uuid.uuid7(),
        source=source.slug,
        source_id=source.id,
        team_id=source.team_id,
        schema_id=resolve_schema(source.schema_resolution, payload),
        severity=map_severity(source.severity, payload),
        received_at=datetime.now(UTC),
        payload=payload,
    )
