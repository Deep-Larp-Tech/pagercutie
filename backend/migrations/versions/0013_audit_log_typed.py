"""Typed audit actions and entity types, and indexes for the actor and action filters (ADR-0079).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-21 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT_ACTION = postgresql.ENUM(
    "user.created",
    "user.updated",
    "user.deleted",
    "user.channel_preferences_updated",
    "team.created",
    "team.updated",
    "team.deleted",
    "team.member_added",
    "team.member_role_changed",
    "team.member_removed",
    "team.channel_preferences_updated",
    "team.rotation_updated",
    "source.created",
    "source.updated",
    "source.deleted",
    "source.token_rotated",
    "event_schema.created",
    "rule.created",
    "rule.updated",
    "rule.deleted",
    "runbook.created",
    "runbook.updated",
    "runbook.deleted",
    "alert.created",
    "alert.renotified",
    "alert.acknowledged",
    "alert.resolved",
    "alert.escalated",
    "step.awaiting_approval",
    "step.awaiting_answer",
    "step.awaiting_manual",
    "step.started",
    "step.succeeded",
    "step.failed",
    "step.skipped",
    "step.approved",
    "step.rejected",
    "step.answered",
    "step.done",
    name="audit_action",
)
AUDIT_ENTITY_TYPE = postgresql.ENUM(
    "user",
    "team",
    "source",
    "event_schema",
    "rule",
    "runbook",
    "alert",
    name="audit_entity_type",
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    AUDIT_ACTION.create(bind)
    AUDIT_ENTITY_TYPE.create(bind)
    op.alter_column(
        "audit_log",
        "action",
        type_=AUDIT_ACTION,
        existing_type=sa.String(length=100),
        postgresql_using="action::audit_action",
    )
    op.alter_column(
        "audit_log",
        "entity_type",
        type_=AUDIT_ENTITY_TYPE,
        existing_type=sa.String(length=50),
        postgresql_using="entity_type::audit_entity_type",
    )
    op.create_index("ix_audit_log_actor_at", "audit_log", ["actor_user_id", "at"], unique=False)
    op.create_index("ix_audit_log_action_at", "audit_log", ["action", "at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_audit_log_action_at", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_at", table_name="audit_log")
    op.alter_column(
        "audit_log",
        "entity_type",
        type_=sa.String(length=50),
        existing_type=AUDIT_ENTITY_TYPE,
        postgresql_using="entity_type::text",
    )
    op.alter_column(
        "audit_log",
        "action",
        type_=sa.String(length=100),
        existing_type=AUDIT_ACTION,
        postgresql_using="action::text",
    )
    bind = op.get_bind()
    AUDIT_ENTITY_TYPE.drop(bind)
    AUDIT_ACTION.drop(bind)
