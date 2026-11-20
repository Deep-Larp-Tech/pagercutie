import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pagercutie.core.models import Base
from pagercutie.persons.models import Person
from pagercutie.skills.models import Skill


class LarpEvent(Base):
    """Append-only ledger: each event moved the person's Elo by `elo_delta` when it was recorded."""

    __tablename__ = "larp_events"
    __table_args__ = (CheckConstraint("believability BETWEEN 1 AND 10", name="believability_range"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id", ondelete="RESTRICT"), index=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    believability: Mapped[int]
    description: Mapped[str] = mapped_column(String(2000))
    location: Mapped[str | None] = mapped_column(String(100))
    elo_delta: Mapped[int]

    # lazy="raise": async code must say what it loads (selectinload) instead of tripping over implicit IO.
    person: Mapped[Person] = relationship(lazy="raise")
    skill: Mapped[Skill] = relationship(lazy="raise")
