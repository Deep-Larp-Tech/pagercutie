"""Runbooks with their original text and parsed steps (ADR-0018), soft-deleted through `deleted_at`.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-20 22:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "runbooks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column(
            "format",
            sa.Enum("structured", "markdown", "text", "link", name="runbook_format"),
            nullable=False,
        ),
        sa.Column("original", sa.Text(), nullable=False),
        sa.Column("attach", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_runbooks_team_id_teams"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runbooks")),
    )
    op.create_index(op.f("ix_runbooks_team_id"), "runbooks", ["team_id"], unique=False)
    op.create_index(
        "ix_runbooks_slug", "runbooks", ["slug"], unique=True, postgresql_where=sa.text("deleted_at IS NULL")
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_runbooks_slug", table_name="runbooks", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_index(op.f("ix_runbooks_team_id"), table_name="runbooks")
    op.drop_table("runbooks")
    sa.Enum(name="runbook_format").drop(op.get_bind())
