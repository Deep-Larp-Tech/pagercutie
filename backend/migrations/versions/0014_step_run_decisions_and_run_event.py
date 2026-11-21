"""Executor state: `step_runs.decision`, `step_runs.occurrences_at_run` and `runbook_runs.event`.

`decision` is the latest human decision on a step, applied by the executor. `occurrences_at_run` is the baseline for
detecting a failed `retry_workflow`. `event` is the alert's first event, which step templates render against.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-21 06:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

step_decision = postgresql.ENUM("approve", "reject", "yes", "no", "done", name="step_decision", create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    step_decision.create(op.get_bind())
    op.add_column("step_runs", sa.Column("decision", step_decision, nullable=True))
    op.add_column("step_runs", sa.Column("occurrences_at_run", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_step_runs_occurrences_at_run_positive"),
        "step_runs",
        "occurrences_at_run IS NULL OR occurrences_at_run >= 1",
    )
    # No released version creates runbook runs yet (`start_run` is not implemented), so NOT NULL without a default
    # keeps rolling updates safe (SPEC §12.2).
    op.add_column("runbook_runs", sa.Column("event", postgresql.JSONB(astext_type=sa.Text()), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runbook_runs", "event")
    op.drop_constraint(op.f("ck_step_runs_occurrences_at_run_positive"), "step_runs", type_="check")
    op.drop_column("step_runs", "occurrences_at_run")
    op.drop_column("step_runs", "decision")
    step_decision.drop(op.get_bind())
