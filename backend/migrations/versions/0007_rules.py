"""Rules owned by a team or by one user (ADR-0026).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-20 22:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("schema_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dedup", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("routing", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("presentation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("runbook_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("num_nonnulls(team_id, user_id) = 1", name=op.f("ck_rules_one_owner")),
        sa.ForeignKeyConstraint(
            ["runbook_id"], ["runbooks.id"], name=op.f("fk_rules_runbook_id_runbooks"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_rules_team_id_teams"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_rules_user_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rules")),
    )
    op.create_index(op.f("ix_rules_runbook_id"), "rules", ["runbook_id"], unique=False)
    op.create_index(op.f("ix_rules_team_id"), "rules", ["team_id"], unique=False)
    op.create_index(op.f("ix_rules_user_id"), "rules", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_rules_user_id"), table_name="rules")
    op.drop_index(op.f("ix_rules_team_id"), table_name="rules")
    op.drop_index(op.f("ix_rules_runbook_id"), table_name="rules")
    op.drop_table("rules")
