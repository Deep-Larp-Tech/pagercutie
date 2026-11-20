import uuid

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.core.models import Base


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (CheckConstraint("difficulty BETWEEN 1 AND 10", name="difficulty_range"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    difficulty: Mapped[int]
