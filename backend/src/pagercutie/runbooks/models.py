"""Runbooks."""

import uuid

from pydantic import TypeAdapter
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.core.models import Base, CreatedAtMixin, IdMixin, PydanticJSONB, UpdatedAtMixin, str_enum
from pagercutie.rules.ast import Condition
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import Step


class Runbook(IdMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """A team's runbook: the `original` text as written and the steps parsed from it (SPEC §11, ADR-0018)."""

    __tablename__ = "runbooks"

    slug: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    format: Mapped[RunbookFormat] = mapped_column(str_enum(RunbookFormat, "runbook_format"))
    original: Mapped[str] = mapped_column(Text)
    attach: Mapped[Condition | None] = mapped_column(PydanticJSONB(TypeAdapter(Condition)))
    steps: Mapped[list[Step]] = mapped_column(PydanticJSONB(TypeAdapter(list[Step])))
