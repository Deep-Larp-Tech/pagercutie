"""Soft delete for users: `deleted_at`, and email unique among active users only.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-20 23:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")
    op.create_index("ix_users_email", "users", ["email"], unique=True, postgresql_where=sa.text("deleted_at IS NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_users_email", table_name="users", postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])
    op.drop_column("users", "deleted_at")
