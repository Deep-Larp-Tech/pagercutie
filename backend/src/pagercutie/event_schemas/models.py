import uuid

from pydantic import JsonValue
from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.core.models import Base, CreatedAtMixin, IdMixin


class EventSchema(IdMixin, CreatedAtMixin, Base):
    """One immutable version of a schema (SCH-3). There is no delete, so rules and sources reference it by id only."""

    __tablename__ = "event_schemas"
    __table_args__ = (
        UniqueConstraint("name", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    name: Mapped[str] = mapped_column(String(50))
    version: Mapped[int]
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str | None] = mapped_column(String(2000))
    # A JSON Schema 2020-12 document (ADR-0011), validated by the service before it is stored.
    json_schema: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
