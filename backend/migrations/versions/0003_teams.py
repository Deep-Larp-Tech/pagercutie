"""Teams with their channel preferences, memberships and on-call rotations (ADR-0025, ADR-0027).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20 22:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("channel_preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("slug", name=op.f("uq_teams_slug")),
    )
    op.create_table(
        "memberships",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("lead", "member", "viewer", name="team_role", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_memberships_team_id_teams"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("team_id", "user_id", name=op.f("pk_memberships")),
    )
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    op.create_table(
        "rotations",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column(
            "handoff_day",
            sa.Enum(
                "mon",
                "tue",
                "wed",
                "thu",
                "fri",
                "sat",
                "sun",
                name="weekday",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("handoff_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_rotations_team_id_teams"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("team_id", name=op.f("pk_rotations")),
    )
    op.create_table(
        "rotation_members",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("position >= 0", name=op.f("ck_rotation_members_position_non_negative")),
        sa.ForeignKeyConstraint(
            ["team_id"], ["rotations.team_id"], name=op.f("fk_rotation_members_team_id_rotations"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_rotation_members_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("team_id", "position", name=op.f("pk_rotation_members")),
    )
    op.create_index(op.f("ix_rotation_members_user_id"), "rotation_members", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_rotation_members_user_id"), table_name="rotation_members")
    op.drop_table("rotation_members")
    op.drop_table("rotations")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("teams")
