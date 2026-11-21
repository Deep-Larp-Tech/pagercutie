"""Delivery `received_at`: when ingest received the event, the start of the end-to-end latency (SPEC §13).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-21 06:39:09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("deliveries", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE deliveries SET received_at = created_at")
    op.alter_column("deliveries", "received_at", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("deliveries", "received_at")
