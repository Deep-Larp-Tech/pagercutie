"""Entrypoints of the ingest stage."""

import hmac
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import jsonschema_rs
import orjson
import structlog
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

log = structlog.get_logger("ingest")

# A team's latest schemas, as stored (ADR-0065).
type TeamSchemaQuery = Callable[[uuid.UUID], Awaitable[Sequence[TeamSchema]]]
# A team's latest schemas, compiled (ADR-0103).
type SchemaLoader = Callable[[uuid.UUID], Awaitable[Sequence[CompiledSchema]]]


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
    """The body as a JSON object; adapters deliver JSON whatever their wire format (SPEC §4.2)."""
    try:
        payload: JsonValue = orjson.loads(body)
    except orjson.JSONDecodeError as e:
        raise EventRejected(RejectReason.UNDECODABLE, [FieldError((), f"not valid JSON: {e}")]) from e
    if not isinstance(payload, dict):
        raise EventRejected(RejectReason.UNDECODABLE, [FieldError((), "must be a JSON object")])
    return payload


@dataclass(frozen=True)
class CompiledSchema:
    """One of a team's latest schemas with its validator."""

    schema: TeamSchema
    # None when the stored document no longer compiles: the schema never matches.
    validator: jsonschema_rs.Draft202012Validator | None
    # Top-level `required` keys, then top-level `properties`; higher is more specific.
    specificity: tuple[int, int]


def specificity(json_schema: Mapping[str, JsonValue]) -> tuple[int, int]:
    """Rank of a matching schema: top-level `required` keys, then top-level `properties`; higher is more specific."""
    required = json_schema.get("required")
    properties = json_schema.get("properties")
    return (
        len(required) if isinstance(required, list) else 0,
        len(properties) if isinstance(properties, dict) else 0,
    )


def compile_schema(schema: TeamSchema) -> CompiledSchema:
    """Compile `schema` offline, so a remote `$ref` never makes ingest fetch URLs; one that does not compile is logged
    and never matches, so one bad schema cannot block the team's other events."""
    try:
        validator = jsonschema_rs.Draft202012Validator(schema.json_schema, offline=True)
    except jsonschema_rs.ValidationError:
        log.exception("ingest.schema_unreadable", message="Schema skipped: it does not compile", schema_id=schema.id)
        validator = None
    return CompiledSchema(schema=schema, validator=validator, specificity=specificity(schema.json_schema))


def team_schema_query(sessionmaker: async_sessionmaker[AsyncSession]) -> TeamSchemaQuery:
    """Queries a team's latest schemas in a session of its own."""

    async def query(team_id: uuid.UUID) -> Sequence[TeamSchema]:
        async with sessionmaker() as session:
            return await latest_team_schemas(session, team_id)

    return query


class SchemaCache:
    """Each team's latest schemas, compiled, cached per replica (ADR-0103).

    `invalidate` runs on `NOTIFY schemas_changed` and when the listening connection is lost. Validators are kept by
    schema version ID across invalidations, since a version's document never changes (SCH-3).
    """

    def __init__(self, query: TeamSchemaQuery) -> None:
        self._query = query
        self._teams: dict[uuid.UUID, Sequence[CompiledSchema]] = {}
        self._compiled: dict[uuid.UUID, CompiledSchema] = {}
        # Bumped by `invalidate`, so a load that started before it does not store what it read.
        self._generation = 0

    async def load(self, team_id: uuid.UUID) -> Sequence[CompiledSchema]:
        """The team's latest schemas; queried and compiled on the first event after an invalidation."""
        cached = self._teams.get(team_id)
        if cached is not None:
            return cached
        generation = self._generation
        compiled = [self._compile(schema) for schema in await self._query(team_id)]
        if generation == self._generation:
            self._teams[team_id] = compiled
        return compiled

    def invalidate(self) -> None:
        """Forget every team's schema list; the next event of each team queries it again."""
        self._teams = {}
        self._generation += 1

    def _compile(self, schema: TeamSchema) -> CompiledSchema:
        compiled = self._compiled.get(schema.id)
        if compiled is None:
            compiled = self._compiled[schema.id] = compile_schema(schema)
        return compiled


def matches(schema: CompiledSchema, payload: Mapping[str, JsonValue]) -> bool:
    """Whether `payload` is valid against `schema`; a schema that does not compile never matches."""
    return schema.validator is not None and schema.validator.is_valid(dict(payload))


def resolve_schema(schemas: Sequence[CompiledSchema], payload: Mapping[str, JsonValue]) -> TeamSchema:
    """The most specific of the team's schemas that `payload` is valid against (SPEC §7, ADR-0065).

    Raises `EventRejected` (`SCHEMA_UNRESOLVED`) when none matches or the most specific matches tie.
    """
    candidates = [schema for schema in schemas if matches(schema, payload)]
    if not candidates:
        raise EventRejected(RejectReason.SCHEMA_UNRESOLVED, [FieldError((), "matches no event schema of the team")])
    best = max(schema.specificity for schema in candidates)
    winners = [schema.schema for schema in candidates if schema.specificity == best]
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


async def normalise(raw: RawEvent, load_schemas: SchemaLoader) -> Event:
    """Decode `raw` and resolve its schema among its source team's into an `Event`.

    Raises `EventRejected` for input that cannot be decoded or matches no single schema.
    """
    source = raw.source
    payload = decode(raw.body)
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
