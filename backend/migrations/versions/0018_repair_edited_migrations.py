"""Apply the changes once made inside 0005 and 0006: drop `sources.schema_resolution`, soft-delete runbooks (ADR-0088).

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-21 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # IF [NOT] EXISTS: databases created from the edited 0005 and 0006 already have these changes (ADR-0088).
    op.execute("ALTER TABLE sources DROP COLUMN IF EXISTS schema_resolution")
    op.execute("ALTER TABLE runbooks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE runbooks DROP CONSTRAINT IF EXISTS uq_runbooks_slug")
    # ADR-0068: a slug is unique among active runbooks only.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_runbooks_slug ON runbooks (slug) WHERE deleted_at IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_runbooks_slug", table_name="runbooks", postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_unique_constraint(op.f("uq_runbooks_slug"), "runbooks", ["slug"])
    op.drop_column("runbooks", "deleted_at")
    op.add_column(
        "sources",
        sa.Column(
            "schema_resolution",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
