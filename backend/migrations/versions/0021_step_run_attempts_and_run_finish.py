"""Executor state: step run leases, attempt keys, error counts and trace links; `runbook_runs.finished_at`.

`run_at` keeps one meaning, when the executor looks at the step next; the claim's lease moves to `lease_until`.
`attempt_key` is the idempotency key of the action attempt in progress, `acted_at` when that attempt started, `errors`
the claims that ended without an outcome (ADR-0103). `finished_at` makes a run's end a fact instead of an audit entry
only (ADR-0105).

Revision ID: 0021
Revises: 0019
Create Date: 2026-11-21 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("step_runs", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("step_runs", sa.Column("attempt_key", sa.Uuid(), nullable=True))
    op.add_column("step_runs", sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("step_runs", sa.Column("errors", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("step_runs", sa.Column("traceparent", sa.Text(), nullable=True))
    op.create_check_constraint(op.f("ck_step_runs_errors_non_negative"), "step_runs", "errors >= 0")
    op.add_column("runbook_runs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    # Runs whose steps are all final finished before this column existed; their `runbook_run.finished` entry exists.
    op.execute(
        sa.text(
            "UPDATE runbook_runs r SET finished_at = now() WHERE NOT EXISTS ("
            "SELECT 1 FROM step_runs s WHERE s.run_id = r.id AND s.status NOT IN ('succeeded', 'failed', 'skipped'))"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runbook_runs", "finished_at")
    op.drop_constraint(op.f("ck_step_runs_errors_non_negative"), "step_runs", type_="check")
    op.drop_column("step_runs", "traceparent")
    op.drop_column("step_runs", "errors")
    op.drop_column("step_runs", "acted_at")
    op.drop_column("step_runs", "attempt_key")
    op.drop_column("step_runs", "lease_until")
