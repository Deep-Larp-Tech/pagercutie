"""Audit actions `runbook_run.started`, `runbook_run.finished` and `step.retry_failed`.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-21 13:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ACTIONS = ("runbook_run.started", "runbook_run.finished", "step.retry_failed")


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres 12+ runs ADD VALUE inside a transaction as long as the value is not used in it.
    for action in NEW_ACTIONS:
        op.execute(sa.text(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'"))


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres cannot drop enum values: delete the entries that use them, then swap in a type without them.
    bind = op.get_bind()
    kept = [
        label
        for label in bind.scalars(
            sa.text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'audit_action' ORDER BY e.enumsortorder"
            )
        )
        if label not in NEW_ACTIONS
    ]
    actions = ", ".join(f"'{action}'" for action in NEW_ACTIONS)
    op.execute(sa.text(f"DELETE FROM audit_log WHERE action IN ({actions})"))
    op.execute(sa.text("ALTER TYPE audit_action RENAME TO audit_action_old"))
    op.execute(sa.text("CREATE TYPE audit_action AS ENUM (" + ", ".join(f"'{label}'" for label in kept) + ")"))
    op.execute(sa.text("ALTER TABLE audit_log ALTER COLUMN action TYPE audit_action USING action::text::audit_action"))
    op.execute(sa.text("DROP TYPE audit_action_old"))
