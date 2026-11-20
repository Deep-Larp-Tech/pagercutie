"""Event schemas: immutable JSON Schema 2020-12 versions, unique by name and version (ADR-0011).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20 22:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "event_schemas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("json_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version >= 1", name=op.f("ck_event_schemas_version_positive")),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_event_schemas_team_id_teams"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_schemas")),
        sa.UniqueConstraint("name", "version", name=op.f("uq_event_schemas_name_version")),
    )
    op.create_index(op.f("ix_event_schemas_team_id"), "event_schemas", ["team_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_event_schemas_team_id"), table_name="event_schemas")
    op.drop_table("event_schemas")
