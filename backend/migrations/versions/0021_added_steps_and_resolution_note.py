"""Steps added during an incident and the resolution note (RUN-7, ADR-0098).

`step_runs.added_by` names the person who added a step to a run; null for steps copied from the runbook.
`alerts.resolution_note` is what fixed the alert, as written by the person who resolved it. Audit action `step.added`.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-21 16:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ACTIONS = ("step.added",)


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable columns, so replicas on the previous version keep writing rows during a rolling update (SPEC §12.2).
    op.add_column("step_runs", sa.Column("added_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_step_runs_added_by_users"), "step_runs", "users", ["added_by"], ["id"], ondelete="RESTRICT"
    )
    op.add_column("alerts", sa.Column("resolution_note", sa.Text(), nullable=True))
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
    op.drop_column("alerts", "resolution_note")
    op.drop_constraint(op.f("fk_step_runs_added_by_users"), "step_runs", type_="foreignkey")
    op.drop_column("step_runs", "added_by")
