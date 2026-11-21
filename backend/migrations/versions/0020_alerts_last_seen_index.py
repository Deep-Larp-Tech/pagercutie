"""Alert feed index on `(last_seen_at, id)`, the `GET /alerts` order.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-21 09:08:01

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_alerts_last_seen_at_id", "alerts", ["last_seen_at", "id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_alerts_last_seen_at_id", table_name="alerts")
