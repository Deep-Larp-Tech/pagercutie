"""Persons, skills and LARPing events.

LARPing events reference persons and skills with ON DELETE RESTRICT: the Elo ledger must not lose rows.

Revision ID: 0001
Revises:
Create Date: 2026-11-20 13:22:48.931805

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "persons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("larp_elo", sa.Integer(), nullable=False),
        sa.CheckConstraint("larp_elo >= 0", name=op.f("ck_persons_larp_elo_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_persons")),
        sa.UniqueConstraint("first_name", "last_name", name=op.f("uq_persons_first_name_last_name")),
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 10", name=op.f("ck_skills_difficulty_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
        sa.UniqueConstraint("name", name=op.f("uq_skills_name")),
    )
    op.create_table(
        "larp_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("believability", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("elo_delta", sa.Integer(), nullable=False),
        sa.CheckConstraint("believability BETWEEN 1 AND 10", name=op.f("ck_larp_events_believability_range")),
        sa.ForeignKeyConstraint(
            ["person_id"], ["persons.id"], name=op.f("fk_larp_events_person_id_persons"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_larp_events_skill_id_skills"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_larp_events")),
    )
    op.create_index(op.f("ix_larp_events_occurred_at"), "larp_events", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_larp_events_person_id"), "larp_events", ["person_id"], unique=False)
    op.create_index(op.f("ix_larp_events_skill_id"), "larp_events", ["skill_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_larp_events_skill_id"), table_name="larp_events")
    op.drop_index(op.f("ix_larp_events_person_id"), table_name="larp_events")
    op.drop_index(op.f("ix_larp_events_occurred_at"), table_name="larp_events")
    op.drop_table("larp_events")
    op.drop_table("skills")
    op.drop_table("persons")
