"""Audit log writes (RUN-5).

Services call `record` in the transaction of the change it describes, so the entry commits or rolls back with it.
Kept apart from `audit/service.py`, which depends on `auth`, so that `auth/service.py` can record logins.
"""

import uuid
from enum import StrEnum

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit.models import AuditEntry


class AuditEntity(StrEnum):
    """`AuditEntry.entity_type`: the kind of entity `AuditEntry.entity_id` names."""

    ALERT = "alert"
    USER = "user"
    TEAM = "team"
    SOURCE = "source"
    EVENT_SCHEMA = "event_schema"


class AuditAction(StrEnum):
    """`AuditEntry.action`, as `<entity>.<past participle>`."""

    ALERT_ACKNOWLEDGED = "alert.acknowledged"
    ALERT_RESOLVED = "alert.resolved"
    STEP_APPROVED = "step.approved"
    STEP_REJECTED = "step.rejected"
    STEP_ANSWERED_YES = "step.answered_yes"
    STEP_ANSWERED_NO = "step.answered_no"
    STEP_DONE = "step.done"
    USER_LOGGED_IN = "user.logged_in"
    USER_LOGGED_OUT = "user.logged_out"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_CHANNEL_PREFERENCES_SET = "user.channel_preferences_set"
    TEAM_CREATED = "team.created"
    TEAM_UPDATED = "team.updated"
    TEAM_DELETED = "team.deleted"
    TEAM_MEMBER_ADDED = "team.member_added"
    TEAM_MEMBER_ROLE_CHANGED = "team.member_role_changed"
    TEAM_MEMBER_REMOVED = "team.member_removed"
    TEAM_ROTATION_SET = "team.rotation_set"
    TEAM_CHANNEL_PREFERENCES_SET = "team.channel_preferences_set"
    SOURCE_CREATED = "source.created"
    SOURCE_UPDATED = "source.updated"
    SOURCE_DELETED = "source.deleted"
    SOURCE_TOKEN_ROTATED = "source.token_rotated"
    EVENT_SCHEMA_CREATED = "event_schema.created"


def record(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    action: AuditAction,
    entity_type: AuditEntity,
    entity_id: uuid.UUID,
    team_id: uuid.UUID | None,
    data: dict[str, JsonValue],
) -> None:
    """Add an audit entry to the session. `actor_user_id` null: done by the system. `team_id` null: admins only.

    `data` must never hold secrets (tokens, token hashes).
    """
    session.add(
        AuditEntry(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            team_id=team_id,
            data=data,
        )
    )
