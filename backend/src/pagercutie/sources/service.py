"""Sources: management (DOMAIN §7) and the view the ingest role loads (SPEC §6)."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import structlog
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select, type_coerce
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth.service import CurrentUser
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.errors import Conflict, FieldError, Forbidden, InvalidInput, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.core.tokens import hash_token, new_token
from pagercutie.sources.models import Source
from pagercutie.sources.schemas import (
    SeverityMapping,
    SourceCreate,
    SourceRead,
    SourceTokenRead,
    SourceType,
    SourceUpdate,
)
from pagercutie.teams.models import Team

log = structlog.get_logger("sources")

# Route of each source type that has an adapter in `pipeline/adapters.py`; other types cannot be created (ADR-0063).
INGEST_PATHS: Final[Mapping[SourceType, str]] = {
    SourceType.WEBHOOK: "/ingest/{source_slug}",
    SourceType.WEBSOCKET: "/ingest/{source_slug}/ws",
}

_SEVERITY = TypeAdapter(SeverityMapping)


@dataclass(frozen=True)
class IngestSource:
    """What ingest needs to accept an event for a source: an enabled source that has an ingest token."""

    id: uuid.UUID
    slug: str
    type: SourceType
    team_id: uuid.UUID
    severity: SeverityMapping
    # SHA-256 of the current ingest token, 32 bytes.
    token_hash: bytes


def ingest_url(source_type: SourceType, slug: str) -> str:
    """Path of the source's adapter route; only types in `INGEST_PATHS` can be created."""
    return INGEST_PATHS[source_type].format(source_slug=slug)


def to_read(source: Source) -> SourceRead:
    return SourceRead(
        id=source.id,
        slug=source.slug,
        name=source.name,
        type=source.type,
        team_id=source.team_id,
        severity=source.severity,
        enabled=source.enabled,
        ingest_url=ingest_url(source.type, source.slug),
        has_token=source.token_hash is not None,
        created_at=source.created_at,
    )


async def _notify_changed(session: AsyncSession) -> None:
    # Every replica reloads its source catalog on it (ADR-0061).
    await notify(session, NotifyChannel.SOURCES_CHANGED)


async def _get_visible(session: AsyncSession, user: CurrentUser, source_id: uuid.UUID) -> Source:
    """The source, or `NotFound` when it is missing or in a team the user cannot see (no existence leak)."""
    source = await session.get(Source, source_id)
    if source is None or not user.can_see_team(source.team_id):
        raise NotFound("Source", source_id)
    return source


async def _get_editable(session: AsyncSession, user: CurrentUser, source_id: uuid.UUID) -> Source:
    source = await _get_visible(session, user, source_id)
    if not user.can_edit_team(source.team_id):
        raise Forbidden("Only members and leads of the team can change its sources")
    return source


async def list_sources(
    session: AsyncSession, user: CurrentUser, pagination: Pagination, team_id: uuid.UUID | None
) -> list[SourceRead]:
    """Sources of the teams the user can see, ordered by slug."""
    statement = select(Source).order_by(Source.slug).limit(pagination.limit).offset(pagination.offset)
    if not user.is_admin:
        statement = statement.where(Source.team_id.in_(user.team_roles.keys()))
    if team_id is not None:
        statement = statement.where(Source.team_id == team_id)
    return [to_read(source) for source in await session.scalars(statement)]


async def get_source(session: AsyncSession, user: CurrentUser, source_id: uuid.UUID) -> SourceRead:
    return to_read(await _get_visible(session, user, source_id))


async def create_source(session: AsyncSession, user: CurrentUser, data: SourceCreate) -> SourceRead:
    if not user.can_edit_team(data.team_id):
        raise Forbidden("Only members and leads of the team can create its sources")
    if await session.get(Team, data.team_id) is None:
        raise NotFound("Team", data.team_id)
    if data.type not in INGEST_PATHS:
        raise InvalidInput([FieldError(("type",), f"source type {data.type} has no ingest adapter yet")])
    # ON CONFLICT instead of catching IntegrityError: no driver error to parse, and the transaction stays usable.
    source = await session.scalar(
        insert(Source)
        .values(
            slug=data.slug,
            name=data.name,
            type=data.type,
            team_id=data.team_id,
            severity=data.severity,
            enabled=data.enabled,
        )
        .on_conflict_do_nothing(index_elements=[Source.slug])
        .returning(Source)
    )
    if source is None:
        raise Conflict(f"Source slug {data.slug} is taken")
    await _notify_changed(session)
    return to_read(source)


async def update_source(
    session: AsyncSession, user: CurrentUser, source_id: uuid.UUID, data: SourceUpdate
) -> SourceRead:
    source = await _get_editable(session, user, source_id)
    if data.name is not None:
        source.name = data.name
    if data.severity is not None:
        source.severity = data.severity
    if data.enabled is not None:
        source.enabled = data.enabled
    await session.flush()
    await _notify_changed(session)
    return to_read(source)


async def delete_source(session: AsyncSession, user: CurrentUser, source_id: uuid.UUID) -> None:
    source = await _get_editable(session, user, source_id)
    await session.delete(source)
    await session.flush()
    await _notify_changed(session)


async def rotate_token(session: AsyncSession, user: CurrentUser, source_id: uuid.UUID) -> SourceTokenRead:
    """Stores the hash of a new ingest token and returns the token; the previous one stops working on commit."""
    source = await _get_editable(session, user, source_id)
    token = new_token()
    source.token_hash = hash_token(token)
    await session.flush()
    await _notify_changed(session)
    return SourceTokenRead(token=token)


async def load_ingest_sources(session: AsyncSession) -> list[IngestSource]:
    """Every enabled source that has an ingest token. A row whose stored config no longer validates is logged and
    skipped, so one bad source cannot stop the others from loading (ADR-0062)."""
    rows = await session.execute(
        select(
            Source.id,
            Source.slug,
            Source.type,
            Source.team_id,
            # Raw JSON, validated per row below instead of by the column type for the whole result.
            type_coerce(Source.severity, JSONB),
            Source.token_hash,
        ).where(Source.enabled, Source.token_hash.is_not(None))
    )
    sources: list[IngestSource] = []
    for source_id, slug, source_type, team_id, severity, token_hash in rows:
        try:
            severity_mapping = _SEVERITY.validate_python(severity)
        except ValidationError:
            log.exception("sources.unreadable", message="Source skipped: stored config does not validate", slug=slug)
            continue
        if token_hash is None:
            continue
        sources.append(
            IngestSource(
                id=source_id,
                slug=slug,
                type=source_type,
                team_id=team_id,
                severity=severity_mapping,
                token_hash=token_hash,
            )
        )
    return sources
