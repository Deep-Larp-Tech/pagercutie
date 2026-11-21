"""Delivery statuses `undeliverable` and `cancelled` (ADR-0110); permanent failures move to `undeliverable`.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-21 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_STATUSES = ("undeliverable", "cancelled")


def upgrade() -> None:
    """Upgrade schema."""
    # A new enum value cannot be used in the transaction that adds it, so the values commit on their own first.
    with op.get_context().autocommit_block():
        for status in NEW_STATUSES:
            op.execute(sa.text(f"ALTER TYPE delivery_status ADD VALUE IF NOT EXISTS '{status}'"))
    # Before this revision a permanent failure was `failed` with no `retry_at` (ADR-0082).
    op.execute(sa.text("UPDATE deliveries SET status = 'undeliverable' WHERE status = 'failed' AND retry_at IS NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres cannot drop enum values: map the rows back, then swap in a type without the new values.
    op.execute(
        sa.text(
            "UPDATE deliveries SET status = 'failed', retry_at = NULL WHERE status IN ('undeliverable', 'cancelled')"
        )
    )
    bind = op.get_bind()
    kept = [
        label
        for label in bind.scalars(
            sa.text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'delivery_status' ORDER BY e.enumsortorder"
            )
        )
        if label not in NEW_STATUSES
    ]
    op.execute(sa.text("DROP INDEX IF EXISTS ix_deliveries_undelivered"))
    op.execute(sa.text("ALTER TYPE delivery_status RENAME TO delivery_status_old"))
    op.execute(sa.text("CREATE TYPE delivery_status AS ENUM (" + ", ".join(f"'{label}'" for label in kept) + ")"))
    op.execute(
        sa.text("ALTER TABLE deliveries ALTER COLUMN status TYPE delivery_status USING status::text::delivery_status")
    )
    op.execute(sa.text("DROP TYPE delivery_status_old"))
    op.create_index(
        "ix_deliveries_undelivered",
        "deliveries",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )
