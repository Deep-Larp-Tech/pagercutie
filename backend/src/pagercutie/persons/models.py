import uuid

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.core.models import Base
from pagercutie.persons.elo import DEFAULT_ELO


class Person(Base):
    __tablename__ = "persons"
    __table_args__ = (
        # Natural key used by the importer to find existing persons.
        UniqueConstraint("first_name", "last_name"),
        CheckConstraint("larp_elo >= 0", name="larp_elo_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    larp_elo: Mapped[int] = mapped_column(default=DEFAULT_ELO)
