import uuid

from pydantic import TypeAdapter
from sqlalchemy import CheckConstraint, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.core.models import Base, CreatedAtMixin, IdMixin, PydanticJSONB, UpdatedAtMixin
from pagercutie.rules.ast import Condition
from pagercutie.rules.schemas import Dedup, Presentation, Routing


class Rule(IdMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """Owned by a team or, for a personal rule, by one user (ADR-0026): exactly one of the two is set."""

    __tablename__ = "rules"
    __table_args__ = (CheckConstraint("num_nonnulls(team_id, user_id) = 1", name="one_owner"),)

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(2000))
    enabled: Mapped[bool]
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    # Event schemas are never deleted, so no foreign keys are lost by using an array. Empty: any schema.
    schema_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid()))
    condition: Mapped[Condition] = mapped_column(PydanticJSONB(TypeAdapter(Condition)))
    dedup: Mapped[Dedup] = mapped_column(PydanticJSONB(TypeAdapter(Dedup)))
    routing: Mapped[Routing] = mapped_column(PydanticJSONB(TypeAdapter(Routing)))
    presentation: Mapped[Presentation] = mapped_column(PydanticJSONB(TypeAdapter(Presentation)))
    runbook_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runbooks.id", ondelete="RESTRICT"), index=True)
