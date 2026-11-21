"""Event schemas.

Permissions follow DOMAIN.md §4: every authenticated user reads every schema; `member` or `lead` of the owning team,
or an admin, creates one. Versions are immutable (SCH-3), so there is no update or delete. A `name` belongs to the
team that created its first version. Every write issues `NOTIFY schemas_changed` (SPEC §5.3, §7).
"""

import uuid

import jsonschema_rs
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth.deps import CurrentUser
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.errors import Conflict, FieldError, Forbidden, InvalidInput, NotFound, NotImplementedYet
from pagercutie.core.schemas import Pagination
from pagercutie.event_schemas.models import EventSchema
from pagercutie.event_schemas.schemas import (
    EventSchemaCreate,
    EventSchemaRead,
    SchemaValidateRequest,
    SchemaValidateResult,
)
from pagercutie.teams.models import Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.schemas import GlobalRole

_EVENT_SCHEMA = "Event schema"
_WRITER_ROLES = {TeamRole.MEMBER, TeamRole.LEAD}
_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


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
    schema = await session.scalar(
        insert(EventSchema)
        .values(**data.model_dump())
        .on_conflict_do_nothing(index_elements=[EventSchema.name, EventSchema.version])
        .returning(EventSchema)
    )
    if schema is None:
        raise Conflict(f"Event schema {data.name} version {data.version} already exists")
    await notify(session, NotifyChannel.SCHEMAS_CHANGED)
    return EventSchemaRead.model_validate(schema)


async def get_event_schema(session: AsyncSession, schema_id: uuid.UUID) -> EventSchemaRead:
    """Any authenticated user."""
    schema = await session.scalar(select(EventSchema).where(EventSchema.id == schema_id))
    if schema is None:
        raise NotFound(_EVENT_SCHEMA, schema_id)
    return EventSchemaRead.model_validate(schema)


async def validate_event(
    session: AsyncSession, schema_id: uuid.UUID, data: SchemaValidateRequest
) -> SchemaValidateResult:
    """Check a sample payload against the schema."""
    raise NotImplementedYet("Event schema validation")


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
