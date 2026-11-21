"""Entrypoints of the ingest stage."""

import hmac
import math
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import assert_never

import jsonschema_rs
import orjson
import structlog
from google.protobuf import struct_pb2
from google.protobuf.message import DecodeError
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.enums import Severity
from pagercutie.core.errors import FieldError, InvalidInput, SourceSlugNotFound, Unauthenticated
from pagercutie.core.payload import field_value
from pagercutie.core.tokens import hash_token
from pagercutie.event_schemas.service import TeamSchema, latest_team_schemas
from pagercutie.pipeline.messages import Event, RawEvent
from pagercutie.sources.schemas import SeverityMapping, SourceType
from pagercutie.sources.service import IngestSource, load_ingest_sources
from pagercutie.v1 import ingest_pb2

log = structlog.get_logger("ingest")

# The latest version of each schema of a team, queried for every event (ADR-0065).
type SchemaLoader = Callable[[uuid.UUID], Awaitable[Sequence[TeamSchema]]]


class RejectReason(StrEnum):
    """Why ingest rejected an event; the `reason` label of `events_rejected_total` (SPEC §13)."""

    UNDECODABLE = "undecodable"
    SCHEMA_UNRESOLVED = "schema_unresolved"


class EventRejected(InvalidInput):
    """The event cannot be normalised; answered with `422` and the issues (SPEC §7)."""

    def __init__(self, reason: RejectReason, errors: list[FieldError]) -> None:
        super().__init__(errors)
        self.reason = reason


@dataclass(frozen=True)
class SourceCatalog:
    """Snapshot of the enabled sources that have an ingest token, cached per replica (SPEC §6, ADR-0062)."""

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


def decode_json(body: bytes) -> dict[str, JsonValue]:
    """The body as a JSON object; webhook and WebSocket sources send JSON whatever their content type (ADR-0061)."""
    try:
        payload: JsonValue = orjson.loads(body)
    except orjson.JSONDecodeError as e:
        raise EventRejected(RejectReason.UNDECODABLE, [FieldError((), f"not valid JSON: {e}")]) from e
    if not isinstance(payload, dict):
        raise EventRejected(RejectReason.UNDECODABLE, [FieldError((), "must be a JSON object")])
    return payload


# Largest magnitude up to which every integer is exactly representable as a double.
_MAX_EXACT_INT = 2**53


def struct_value(value: struct_pb2.Value, loc: tuple[str | int, ...]) -> JsonValue:
    """A protobuf `Value` as JSON. Integral numbers within ±2^53 become `int`, so `500` from a Struct matches
    `"type": "integer"` and fingerprints like `500` from a JSON body (ADR-0097)."""
    match value.WhichOneof("kind"):
        case "null_value" | None:
            return None
        case "number_value":
            number = value.number_value
            if not math.isfinite(number):
                raise EventRejected(RejectReason.UNDECODABLE, [FieldError(loc, "number must be finite")])
            return int(number) if number.is_integer() and abs(number) <= _MAX_EXACT_INT else number
        case "string_value":
            return value.string_value
        case "bool_value":
            return value.bool_value
        case "struct_value":
            return struct_fields(value.struct_value, loc)
        case "list_value":
            return [struct_value(item, (*loc, i)) for i, item in enumerate(value.list_value.values)]
        case unreachable:
            assert_never(unreachable)


def struct_fields(struct: struct_pb2.Struct, loc: tuple[str | int, ...]) -> dict[str, JsonValue]:
    return {key: struct_value(value, (*loc, key)) for key, value in struct.fields.items()}


def decode_protobuf(body: bytes) -> dict[str, JsonValue]:
    """The `payload` of a serialised `pagercutie.v1.Event` as a JSON object (SPEC §4.2)."""
    try:
        event = ingest_pb2.Event.FromString(body)
    except DecodeError as e:
        raise EventRejected(RejectReason.UNDECODABLE, [FieldError((), f"not a pagercutie.v1.Event: {e}")]) from e
    return struct_fields(event.payload, ())


def decode(raw: RawEvent) -> dict[str, JsonValue]:
    """The event body as a JSON object, decoded by the format of the adapter that received it."""
    match raw.source_type:
        case SourceType.WEBHOOK | SourceType.WEBSOCKET:
            return decode_json(raw.body)
        case SourceType.PROTOBUF:
            return decode_protobuf(raw.body)
        case unreachable:
            assert_never(unreachable)


def schema_loader(sessionmaker: async_sessionmaker[AsyncSession]) -> SchemaLoader:
    """Loads a team's latest schemas in a session of its own, one query per event (ADR-0065)."""

    async def load(team_id: uuid.UUID) -> Sequence[TeamSchema]:
        async with sessionmaker() as session:
            return await latest_team_schemas(session, team_id)

    return load


def specificity(json_schema: Mapping[str, JsonValue]) -> tuple[int, int]:
    """Rank of a matching schema: top-level `required` keys, then top-level `properties`; higher is more specific."""
    required = json_schema.get("required")
    properties = json_schema.get("properties")
    return (
        len(required) if isinstance(required, list) else 0,
        len(properties) if isinstance(properties, dict) else 0,
    )


def matches(schema: TeamSchema, payload: Mapping[str, JsonValue]) -> bool:
    """Whether `payload` is valid against `schema`; a stored schema that no longer compiles is logged and never
    matches, so one bad schema cannot block the team's other events."""
    try:
        # offline: a remote `$ref` must not make ingest fetch URLs.
        validator = jsonschema_rs.Draft202012Validator(schema.json_schema, offline=True)
    except jsonschema_rs.ValidationError:
        log.exception("ingest.schema_unreadable", message="Schema skipped: it does not compile", schema_id=schema.id)
        return False
    return validator.is_valid(dict(payload))


def resolve_schema(schemas: Sequence[TeamSchema], payload: Mapping[str, JsonValue]) -> TeamSchema:
    """The most specific of the team's schemas that `payload` is valid against (SPEC §7, ADR-0065).

    Raises `EventRejected` (`SCHEMA_UNRESOLVED`) when none matches or the most specific matches tie.
    """
    candidates = [schema for schema in schemas if matches(schema, payload)]
    if not candidates:
        raise EventRejected(RejectReason.SCHEMA_UNRESOLVED, [FieldError((), "matches no event schema of the team")])
    best = max(specificity(schema.json_schema) for schema in candidates)
    winners = [schema for schema in candidates if specificity(schema.json_schema) == best]
    if len(winners) > 1:
        names = ", ".join(schema.name for schema in winners)
        raise EventRejected(
            RejectReason.SCHEMA_UNRESOLVED, [FieldError((), f"matches several equally specific schemas: {names}")]
        )
    return winners[0]


def map_severity(mapping: SeverityMapping, payload: Mapping[str, JsonValue]) -> Severity:
    """The normalised severity; `mapping.default` when the field is unset, missing or has an unmapped value."""
    if mapping.field is None:
        return mapping.default
    value = field_value(payload, mapping.field)
    if value is None:
        return mapping.default
    return mapping.values.get(as_key(value), mapping.default)


async def normalise(raw: RawEvent, catalog: SourceCatalog, load_schemas: SchemaLoader) -> Event:
    """Authenticate, decode and resolve the schema of `raw` into an `Event`.

    Raises `SourceSlugNotFound` for an unknown, disabled or tokenless source or one of another type, `Unauthenticated`
    for a missing or wrong token and `EventRejected` for input that cannot be decoded or matches no single schema.
    """
    source = authenticate(catalog, raw.source_slug, raw.source_type, raw.token)
    payload = decode(raw)
    schema = resolve_schema(await load_schemas(source.team_id), payload)
    return Event(
        event_id=uuid.uuid7(),
        source=source.slug,
        source_id=source.id,
        team_id=source.team_id,
        schema_id=schema.id,
        schema_name=schema.name,
        severity=map_severity(source.severity, payload),
        received_at=datetime.now(UTC),
        payload=payload,
    )
