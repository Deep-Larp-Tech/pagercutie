"""Audit log: reads, and `record`, which the services that make a change call in the same transaction (RUN-5).

Permissions follow DOMAIN.md §4: any role in the team an entry belongs to reads it, admins read all entries. Entries
without a team (`team_id` null) are admin-only. Nothing writes entries through the API.

`data` never holds secrets (tokens, token hashes). An update stores the changed fields as `{"before", "after"}`; a
create or delete stores the fields that identify the entity, since the row may be gone later.
"""

import uuid
from collections.abc import Mapping

from pydantic import JsonValue
from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction, AuditEntryRead, AuditQuery, entity_type_of
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.schemas import Pagination
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_audit_entries(
    session: AsyncSession, actor: CurrentUser, pagination: Pagination, filters: AuditQuery
) -> list[AuditEntryRead]:
    """Newest first. A non-admin filtering by a team they are not in gets an empty list, not a 403."""
    statement = select(AuditEntry, User.display_name).outerjoin(User, User.id == AuditEntry.actor_user_id)
    if actor.role is not GlobalRole.ADMIN:
        statement = statement.where(AuditEntry.team_id.in_(actor.team_roles) if actor.team_roles else false())
    if filters.team_id is not None:
        statement = statement.where(AuditEntry.team_id == filters.team_id)
    if filters.without_team:
        statement = statement.where(AuditEntry.team_id.is_(None))
    if filters.entity_type is not None:
        statement = statement.where(AuditEntry.entity_type == filters.entity_type)
    if filters.entity_id is not None:
        statement = statement.where(AuditEntry.entity_id == filters.entity_id)
    if filters.actor_user_id is not None:
        statement = statement.where(AuditEntry.actor_user_id == filters.actor_user_id)
    if filters.system:
        statement = statement.where(AuditEntry.actor_user_id.is_(None))
    if filters.action:
        statement = statement.where(AuditEntry.action.in_(filters.action))
    if filters.since is not None:
        statement = statement.where(AuditEntry.at >= filters.since)
    if filters.until is not None:
        statement = statement.where(AuditEntry.at < filters.until)
    # UUIDv7 ids break ties between entries with the same timestamp.
    rows = await session.execute(
        statement.order_by(AuditEntry.at.desc(), AuditEntry.id.desc()).limit(pagination.limit).offset(pagination.offset)
    )
    return [
        AuditEntryRead.model_validate(entry).model_copy(update={"actor_name": actor_name}) for entry, actor_name in rows
    ]


# --- Writes (called by the services that make the changes) -----------------------------------------------------


def record(
    session: AsyncSession,
    actor_user_id: uuid.UUID | None,
    action: AuditAction,
    entity_id: uuid.UUID,
    team_id: uuid.UUID | None,
    data: Mapping[str, JsonValue],
) -> None:
    """Add an entry to the session; it commits or rolls back with the change it records."""
    session.add(
        AuditEntry(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type_of(action),
            entity_id=entity_id,
            team_id=team_id,
            data=dict(data),
        )
    )


def changes(before: Mapping[str, JsonValue], after: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """`{"before": {...}, "after": {...}}` with only the keys whose value differs; both empty when nothing did."""
    changed = [key for key in after if before.get(key) != after[key]]
    return {
        "before": {key: before.get(key) for key in changed},
        "after": {key: after[key] for key in changed},
    }
