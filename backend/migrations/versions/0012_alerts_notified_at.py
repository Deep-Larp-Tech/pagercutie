"""When an alert last notified: `notified_at`, which decides renotification (SPEC §5.2).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-21 05:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # No released version inserts alerts yet, so NOT NULL without a default keeps rolling updates safe (SPEC §12.2).
    op.add_column("alerts", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE alerts SET notified_at = first_seen_at")
    op.alter_column("alerts", "notified_at", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("alerts", "notified_at")
