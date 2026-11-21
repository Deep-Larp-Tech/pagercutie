"""Delivery lease, trace context and digest link (SPEC §9, §10, §13); claim index for pending and failed rows.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-21 05:45:57

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
    op.add_column("deliveries", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deliveries", sa.Column("traceparent", sa.Text(), nullable=True))
    op.add_column("deliveries", sa.Column("digest_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_deliveries_digest_id_deliveries"),
        "deliveries",
        "deliveries",
        ["digest_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_index("ix_deliveries_retry_at", table_name="deliveries", postgresql_where=sa.text("status = 'failed'"))
    op.create_index(
        "ix_deliveries_undelivered",
        "deliveries",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_deliveries_undelivered",
        table_name="deliveries",
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )
    op.create_index(
        "ix_deliveries_retry_at",
        "deliveries",
        ["retry_at"],
        unique=False,
        postgresql_where=sa.text("status = 'failed'"),
    )
    op.drop_constraint(op.f("fk_deliveries_digest_id_deliveries"), "deliveries", type_="foreignkey")
    op.drop_column("deliveries", "digest_id")
    op.drop_column("deliveries", "traceparent")
    op.drop_column("deliveries", "lease_until")
