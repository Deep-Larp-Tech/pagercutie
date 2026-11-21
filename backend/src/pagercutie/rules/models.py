"""Rules."""

import uuid
from datetime import datetime

from pydantic import TypeAdapter
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.core.models import Base, CreatedAtMixin, IdMixin, PydanticJSONB, UpdatedAtMixin
from pagercutie.rules.ast import Condition
from pagercutie.rules.schemas import Dedup, Presentation, Routing


class Rule(IdMixin, CreatedAtMixin, UpdatedAtMixin, Base, kw_only=True):
    """A rule owned by a team, or by one user for a personal rule (ADR-0026); exactly one owner column is set."""

    __tablename__ = "rules"
    __table_args__ = (CheckConstraint("num_nonnulls(team_id, user_id) = 1", name="one_owner"),)

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    enabled: Mapped[bool]
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    schema_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid()))
    condition: Mapped[Condition] = mapped_column(PydanticJSONB(TypeAdapter(Condition)))
    dedup: Mapped[Dedup] = mapped_column(PydanticJSONB(TypeAdapter(Dedup)))
    routing: Mapped[Routing] = mapped_column(PydanticJSONB(TypeAdapter(Routing)))
    presentation: Mapped[Presentation] = mapped_column(PydanticJSONB(TypeAdapter(Presentation)))
    runbook_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runbooks.id", ondelete="RESTRICT"), index=True, default=None
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, sort_order=1)
