"""Event schemas: management and the view ingest queries for every event.

Permissions follow DOMAIN.md §4: every authenticated user reads every schema; `member` or `lead` of the owning team,
or an admin, creates one. Versions are immutable (SCH-3), so there is no update or delete. A `name` belongs to the
team that created its first version. Every write issues `NOTIFY schemas_changed` (SPEC §5.3, §7).
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import islice

import jsonschema_rs
from pydantic import JsonValue
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit import service as audit
from pagercutie.audit.schemas import AuditAction
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.db import NotifyChannel, notify, violates_unique
from pagercutie.core.errors import Conflict, FieldError, Forbidden, InvalidInput, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.event_schemas.models import EventSchema
from pagercutie.event_schemas.schemas import (
    EventSchemaCreate,
    EventSchemaRead,
    SchemaValidateRequest,
    SchemaValidateResult,
    ValidationIssue,
)
from pagercutie.teams.models import Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.schemas import GlobalRole

_EVENT_SCHEMA = "Event schema"
_WRITER_ROLES = {TeamRole.MEMBER, TeamRole.LEAD}
_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
# Bounds the response for a large payload that fails everywhere; the first issues are enough to fix the sample.
_MAX_ISSUES = 50


# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_event_schemas(
    session: AsyncSession, pagination: Pagination, name: str | None, team_id: uuid.UUID | None
) -> list[EventSchemaRead]:
    """Any authenticated user, so rules can use other teams' events."""
    statement = (
        select(EventSchema)
        .order_by(EventSchema.name, EventSchema.version)
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    if name is not None:
        statement = statement.where(EventSchema.name == name)
    if team_id is not None:
        statement = statement.where(EventSchema.team_id == team_id)
    return [EventSchemaRead.model_validate(schema) for schema in await session.scalars(statement)]


async def create_event_schema(session: AsyncSession, actor: CurrentUser, data: EventSchemaCreate) -> EventSchemaRead:
    """`member` or `lead` of `team_id`, or an admin. Any unused version of at least 1 is accepted."""
    _require_writer(actor, data.team_id)
    if not await session.scalar(select(exists().where(Team.id == data.team_id))):
        # The route declares no 404, so an unknown team is a validation error on the body.
        raise InvalidInput([FieldError(("team_id",), "Team does not exist")])
    _require_draft_2020_12(data.json_schema)
    owner_id = await session.scalar(select(EventSchema.team_id).where(EventSchema.name == data.name).limit(1))
    if owner_id is not None and owner_id != data.team_id:
        raise Conflict(f"Event schema name {data.name} belongs to another team")
    schema = EventSchema(
        name=data.name,
        version=data.version,
        team_id=data.team_id,
        description=data.description,
        json_schema=data.json_schema,
    )
    session.add(schema)
    # No savepoint needed: the Conflict rolls back the request's transaction.
    try:
        await session.flush()
    except IntegrityError as error:
        if violates_unique(error, "uq_event_schemas_name_version"):
            raise Conflict(f"Event schema {data.name} version {data.version} already exists") from None
        raise
    created = EventSchemaRead.model_validate(schema)
    # The JSON Schema document stays on the immutable row (SCH-3); the entry names the version.
    identity: dict[str, JsonValue] = {"name": created.name, "version": created.version}
    audit.record(session, actor.id, AuditAction.EVENT_SCHEMA_CREATED, schema.id, schema.team_id, identity)
    await notify(session, NotifyChannel.SCHEMAS_CHANGED)
    return created


async def get_event_schema(session: AsyncSession, schema_id: uuid.UUID) -> EventSchemaRead:
    """Any authenticated user."""
    schema = await session.scalar(select(EventSchema).where(EventSchema.id == schema_id))
    if schema is None:
        raise NotFound(_EVENT_SCHEMA, schema_id)
    return EventSchemaRead.model_validate(schema)


async def validate_event(
    session: AsyncSession, schema_id: uuid.UUID, data: SchemaValidateRequest
) -> SchemaValidateResult:
    """Any authenticated user. Validates as ingest does (draft 2020-12, offline), so the result predicts ingest; an
    invalid payload is a `200` with `valid` false. Reports at most `_MAX_ISSUES` issues, in the validator's order.
    """
    schema = await get_event_schema(session, schema_id)
    try:
        validator = compile_validator(schema.json_schema)
    except jsonschema_rs.ValidationError as error:
        # Passes the meta-schema but cannot compile offline, e.g. a remote `$ref`; ingest never matches it either.
        issue = ValidationIssue(path="", message=f"The schema does not compile: {error.message}")
        return SchemaValidateResult(valid=False, issues=[issue])
    issues = [
        ValidationIssue(path=_json_pointer(error.instance_path), message=error.message)
        for error in islice(validator.iter_errors(data.payload), _MAX_ISSUES)
    ]
    return SchemaValidateResult(valid=not issues, issues=issues)


def compile_validator(json_schema: Mapping[str, JsonValue]) -> jsonschema_rs.Draft202012Validator:
    """The validator ingest and the sample check share; offline, so a remote `$ref` is never fetched (ADR-0065).

    Raises `jsonschema_rs.ValidationError` when the schema does not compile.
    """
    return jsonschema_rs.Draft202012Validator(dict(json_schema), offline=True)


def _json_pointer(path: Sequence[str | int]) -> str:
    """RFC 6901 pointer for a `jsonschema-rs` instance path; the root is `""`."""
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in path)


@dataclass(frozen=True)
class TeamSchema:
    """The latest version of one of a team's schemas, as ingest matches events against it."""

    id: uuid.UUID
    name: str
    # JSON Schema 2020-12 document (ADR-0011).
    json_schema: dict[str, JsonValue]


async def latest_team_schemas(session: AsyncSession, team_id: uuid.UUID) -> list[TeamSchema]:
    """The highest version of each schema name the team owns, ordered by name (ADR-0065)."""
    rows = await session.execute(
        select(EventSchema.id, EventSchema.name, EventSchema.json_schema)
        .where(EventSchema.team_id == team_id)
        .ext(distinct_on(EventSchema.name))
        .order_by(EventSchema.name, EventSchema.version.desc())
    )
    return [TeamSchema(id=schema_id, name=name, json_schema=json_schema) for schema_id, name, json_schema in rows]


# --- Rules -----------------------------------------------------------------------------------------------------


def _require_writer(actor: CurrentUser, team_id: uuid.UUID) -> None:
    # Checked before any DB access so non-members can't probe which team IDs exist.
    if actor.role is not GlobalRole.ADMIN and actor.team_roles.get(team_id) not in _WRITER_ROLES:
        raise Forbidden("Only members and leads of the owning team, or an admin, can create its event schemas")


def _require_draft_2020_12(json_schema: dict[str, object]) -> None:
    """Rejects other drafts up front: `meta.validate` would pick the draft from `$schema` and fetch unknown ones."""
    declared = json_schema.get("$schema")
    if declared is not None and declared not in {_DRAFT_2020_12, f"{_DRAFT_2020_12}#"}:
        raise InvalidInput([FieldError(("json_schema", "$schema"), f"Must be {_DRAFT_2020_12}")])
    try:
        jsonschema_rs.meta.validate(json_schema)
    except jsonschema_rs.ValidationError as error:
        location = tuple(error.instance_path)
        raise InvalidInput([FieldError(("json_schema", *location), error.message)]) from error
