"""Audit log reads.

Permissions follow DOMAIN.md §4: any role in the team an entry belongs to reads it, admins read all entries. Entries
without a team (`team_id` null) are admin-only. Entries are written by the services that make the changes, never
through the API.
"""

import uuid

from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditEntryRead
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.schemas import Pagination
from pagercutie.users.schemas import GlobalRole

# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_audit_entries(
    session: AsyncSession,
    actor: CurrentUser,
    pagination: Pagination,
    team_id: uuid.UUID | None,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
) -> list[AuditEntryRead]:
    """Newest first. A non-admin filtering by a team they are not in gets an empty list, not a 403."""
    statement = select(AuditEntry)
    if actor.role is not GlobalRole.ADMIN:
        statement = statement.where(AuditEntry.team_id.in_(actor.team_roles) if actor.team_roles else false())
    if team_id is not None:
        statement = statement.where(AuditEntry.team_id == team_id)
    if entity_type is not None:
        statement = statement.where(AuditEntry.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(AuditEntry.entity_id == entity_id)
    # UUIDv7 ids break ties between entries with the same timestamp.
    entries = await session.scalars(
        statement.order_by(AuditEntry.at.desc(), AuditEntry.id.desc()).limit(pagination.limit).offset(pagination.offset)
    )
    return [AuditEntryRead.model_validate(entry) for entry in entries]
