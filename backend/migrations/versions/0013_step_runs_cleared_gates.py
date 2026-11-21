"""Step runs record the gates a person cleared: `guard_answered`, `approved`.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-21 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("step_runs", sa.Column("guard_answered", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("step_runs", sa.Column("approved", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("step_runs", "approved")
    op.drop_column("step_runs", "guard_answered")
