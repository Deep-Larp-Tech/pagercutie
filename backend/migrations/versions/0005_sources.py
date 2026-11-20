"""Event sources with their schema resolution and severity mapping (jsonb), and the ingest token hash.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20 22:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "webhook",
                "websocket",
                "protobuf",
                name="source_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("schema_resolution", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("severity", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_sources_team_id_teams"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint("slug", name=op.f("uq_sources_slug")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sources_token_hash")),
    )
    op.create_index(op.f("ix_sources_team_id"), "sources", ["team_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_sources_team_id"), table_name="sources")
    op.drop_table("sources")
