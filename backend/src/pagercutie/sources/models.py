"""Event sources."""

import uuid

from pydantic import TypeAdapter
from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.core.models import Base, CreatedAtMixin, IdMixin, PydanticJSONB, str_enum
from pagercutie.sources.schemas import SchemaResolution, SeverityMapping, SourceType


class Source(IdMixin, CreatedAtMixin, Base):
    """A producer of events: how ingest picks their schema and reads their severity."""

    __tablename__ = "sources"

    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[SourceType] = mapped_column(str_enum(SourceType, "source_type"))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    schema_resolution: Mapped[SchemaResolution] = mapped_column(PydanticJSONB(TypeAdapter(SchemaResolution)))
    severity: Mapped[SeverityMapping] = mapped_column(PydanticJSONB(TypeAdapter(SeverityMapping)))
    enabled: Mapped[bool]
    # SHA-256 of the ingest token; the token is shown once by `POST /sources/{id}/token`. Null until then.
    token_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), unique=True)
