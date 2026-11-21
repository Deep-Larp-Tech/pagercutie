"""Notification rounds per alert: `notifications`, the sequence in `Renotified` and the delivery IDs.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-21 03:38:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The server default keeps replicas that do not know the column inserting alerts (SPEC §12.2).
    op.add_column("alerts", sa.Column("notifications", sa.Integer(), server_default=sa.text("1"), nullable=False))
    op.create_check_constraint(op.f("ck_alerts_notifications_positive"), "alerts", "notifications >= 1")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_alerts_notifications_positive"), "alerts", type_="check")
    op.drop_column("alerts", "notifications")
