"""Audit actions for logins and logouts (ADR-0079).

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-21 13:00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # AFTER keeps the Postgres order equal to `AuditAction`'s declaration order (ADR-0031).
    op.execute(
        "ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'user.logged_in' AFTER 'user.channel_preferences_updated'"
    )
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'user.logged_out' AFTER 'user.logged_in'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres cannot drop an enum value, and dropping these would mean deleting audit entries. The unused values
    # stay; the downgrade of 0013 drops the whole type.
