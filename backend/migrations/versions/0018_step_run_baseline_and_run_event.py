"""Executor state: `step_runs.occurrences_at_run` and `runbook_runs.event`.

`occurrences_at_run` is the baseline for detecting a failed `retry_workflow`. `event` is the alert's first event, which
step templates render against.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-21 06:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("step_runs", sa.Column("occurrences_at_run", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_step_runs_occurrences_at_run_positive"),
        "step_runs",
        "occurrences_at_run IS NULL OR occurrences_at_run >= 1",
    )
    op.add_column("runbook_runs", sa.Column("event", postgresql.JSONB(astext_type=sa.Text()), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runbook_runs", "event")
    op.drop_constraint(op.f("ck_step_runs_occurrences_at_run_positive"), "step_runs", type_="check")
    op.drop_column("step_runs", "occurrences_at_run")
