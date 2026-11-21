"""Event sources and their ingest tokens.

Permissions follow DOMAIN.md §4: any role in the owning team reads a source, `member` or `lead` creates, edits,
deletes and re-tokens it, admins do everything. A source the actor cannot see answers 404, so non-members cannot
probe which sources exist. Every write issues `NOTIFY schemas_changed` so each replica reloads its source catalog
(SPEC §5.3, §7).
"""

import secrets
import uuid
from typing import assert_never

from sqlalchemy import delete, exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth import service as auth_service
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.errors import Conflict, Forbidden, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.event_schemas.models import EventSchema
from pagercutie.sources.models import Source
from pagercutie.sources.schemas import (
    DiscriminatedSchema,
    FixedSchema,
    SchemaResolution,
    SourceCreate,
    SourceRead,
    SourceTokenRead,
    SourceUpdate,
)
from pagercutie.teams.models import Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.schemas import GlobalRole

_SOURCE = "Source"
_TEAM = "Team"
_EVENT_SCHEMA = "Event schema"
_WRITER_ROLES = {TeamRole.MEMBER, TeamRole.LEAD}


# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_sources(
    session: AsyncSession, actor: CurrentUser, pagination: Pagination, team_id: uuid.UUID | None
) -> list[SourceRead]:
    """Admins see every source, other users the sources of the teams they belong to."""
    statement = select(Source).order_by(Source.id).limit(pagination.limit).offset(pagination.offset)
    if actor.role is not GlobalRole.ADMIN:
        statement = statement.where(Source.team_id.in_(actor.team_roles))
    if team_id is not None:
        statement = statement.where(Source.team_id == team_id)
    return [_to_read(source) for source in await session.scalars(statement)]


async def create_source(session: AsyncSession, actor: CurrentUser, data: SourceCreate) -> SourceRead:
    """`member` or `lead` of `team_id`, or an admin. The token stays null until `rotate_source_token`."""
    _require_writer(actor, data.team_id)
    if not await session.scalar(select(exists().where(Team.id == data.team_id))):
        raise NotFound(_TEAM, data.team_id)
    await _require_schemas_exist(session, data.schema_resolution)
    source = await session.scalar(
        insert(Source)
        .values(
            slug=data.slug,
            name=data.name,
            type=data.type,
            team_id=data.team_id,
            schema_resolution=data.schema_resolution,
            severity=data.severity,
            enabled=data.enabled,
        )
        .on_conflict_do_nothing(index_elements=[Source.slug])
        .returning(Source)
    )
    if source is None:
        raise Conflict(f"A source with slug {data.slug} already exists")
    await notify(session, NotifyChannel.SCHEMAS_CHANGED)
    return _to_read(source)


async def get_source(session: AsyncSession, actor: CurrentUser, source_id: uuid.UUID) -> SourceRead:
    """Any role in the owning team, or an admin."""
    return _to_read(await _load_visible(session, actor, source_id))


async def update_source(
    session: AsyncSession, actor: CurrentUser, source_id: uuid.UUID, data: SourceUpdate
) -> SourceRead:
    """`member` or `lead` of the owning team, or an admin."""
    source = await _load_writable(session, actor, source_id)
    # Omitted or null fields stay unchanged (SourceUpdate docstring).
    changes = {name: value for name, value in data if value is not None}
    if not changes:
        return _to_read(source)
    if data.schema_resolution is not None:
        await _require_schemas_exist(session, data.schema_resolution)
    updated = await session.scalar(update(Source).where(Source.id == source_id).values(**changes).returning(Source))
    if updated is None:
        raise NotFound(_SOURCE, source_id)
    await notify(session, NotifyChannel.SCHEMAS_CHANGED)
    return _to_read(updated)


async def delete_source(session: AsyncSession, actor: CurrentUser, source_id: uuid.UUID) -> None:
    """`member` or `lead` of the owning team, or an admin. Hard delete: no table references a source by foreign key."""
    await _load_writable(session, actor, source_id)
    await session.execute(delete(Source).where(Source.id == source_id))
    await notify(session, NotifyChannel.SCHEMAS_CHANGED)


async def rotate_source_token(session: AsyncSession, actor: CurrentUser, source_id: uuid.UUID) -> SourceTokenRead:
    """`member` or `lead` of the owning team, or an admin. Stores only the hash; the previous token stops working."""
    await _load_writable(session, actor, source_id)
    token = secrets.token_urlsafe(32)
    rotated_id = await session.scalar(
        update(Source)
        .where(Source.id == source_id)
        .values(token_hash=auth_service.hash_token(token))
        .returning(Source.id)
    )
    if rotated_id is None:
        raise NotFound(_SOURCE, source_id)
    await notify(session, NotifyChannel.SCHEMAS_CHANGED)
    return SourceTokenRead(token=token)


# --- Rules -----------------------------------------------------------------------------------------------------


def _is_writer(actor: CurrentUser, team_id: uuid.UUID) -> bool:
    return actor.role is GlobalRole.ADMIN or actor.team_roles.get(team_id) in _WRITER_ROLES


def _require_writer(actor: CurrentUser, team_id: uuid.UUID) -> None:
    # Checked before any DB access so non-members can't probe which team IDs exist.
    if not _is_writer(actor, team_id):
        raise Forbidden("Only members and leads of the owning team, or an admin, can change its sources")


async def _load_visible(session: AsyncSession, actor: CurrentUser, source_id: uuid.UUID) -> Source:
    source = await session.scalar(select(Source).where(Source.id == source_id))
    if source is None or (actor.role is not GlobalRole.ADMIN and source.team_id not in actor.team_roles):
        raise NotFound(_SOURCE, source_id)
    return source


async def _load_writable(session: AsyncSession, actor: CurrentUser, source_id: uuid.UUID) -> Source:
    """404 for a source the actor cannot see, 403 for one they can see but not change (a viewer)."""
    source = await _load_visible(session, actor, source_id)
    _require_writer(actor, source.team_id)
    return source


def _referenced_schema_ids(resolution: SchemaResolution) -> set[uuid.UUID]:
    match resolution:
        case FixedSchema(schema_id=schema_id):
            return {schema_id}
        case DiscriminatedSchema(mapping=mapping):
            return set(mapping.values())
        case _:
            assert_never(resolution)


async def _require_schemas_exist(session: AsyncSession, resolution: SchemaResolution) -> None:
    wanted = _referenced_schema_ids(resolution)
    found = set(await session.scalars(select(EventSchema.id).where(EventSchema.id.in_(wanted))))
    missing = wanted - found
    if missing:
        raise NotFound(_EVENT_SCHEMA, min(missing))


def _to_read(source: Source) -> SourceRead:
    return SourceRead(
        id=source.id,
        slug=source.slug,
        name=source.name,
        type=source.type,
        team_id=source.team_id,
        schema_resolution=source.schema_resolution,
        severity=source.severity,
        enabled=source.enabled,
        ingest_url=f"/ingest/{source.slug}",
        created_at=source.created_at,
    )
