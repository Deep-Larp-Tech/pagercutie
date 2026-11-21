"""Event schemas: the view ingest queries for every event (SPEC §7)."""

import uuid
from dataclasses import dataclass

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.event_schemas.models import EventSchema


@dataclass(frozen=True)
class TeamSchema:
    """The latest version of one of a team's schemas, as ingest matches events against it."""

    id: uuid.UUID
    name: str
    # JSON Schema 2020-12 document (ADR-0011).
    json_schema: dict[str, JsonValue]


async def latest_team_schemas(session: AsyncSession, team_id: uuid.UUID) -> list[TeamSchema]:
    """The highest version of each schema name the team owns, ordered by name (ADR-0061)."""
    rows = await session.execute(
        select(EventSchema.id, EventSchema.name, EventSchema.json_schema)
        .where(EventSchema.team_id == team_id)
        .ext(distinct_on(EventSchema.name))
        .order_by(EventSchema.name, EventSchema.version.desc())
    )
    return [TeamSchema(id=schema_id, name=name, json_schema=json_schema) for schema_id, name, json_schema in rows]
