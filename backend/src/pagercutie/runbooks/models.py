"""Runbooks."""

import uuid
from datetime import datetime

from pydantic import TypeAdapter
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.core.models import Base, CreatedAtMixin, IdMixin, PydanticJSONB, UpdatedAtMixin, str_enum
from pagercutie.rules.ast import Condition
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import Step


class Runbook(IdMixin, CreatedAtMixin, UpdatedAtMixin, Base, kw_only=True):
    """A team's runbook: the `original` text as written and the steps parsed from it (SPEC §11, ADR-0018)."""

    __tablename__ = "runbooks"
    __table_args__ = (
        # Unique among active runbooks only, so a soft-deleted runbook's slug can be reused.
        Index("ix_runbooks_slug", "slug", unique=True, postgresql_where=text("deleted_at IS NULL")),
    )

    slug: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(100))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    format: Mapped[RunbookFormat] = mapped_column(str_enum(RunbookFormat, "runbook_format"))
    original: Mapped[str] = mapped_column(Text)
    attach: Mapped[Condition | None] = mapped_column(PydanticJSONB(TypeAdapter(Condition)), default=None)
    steps: Mapped[list[Step]] = mapped_column(PydanticJSONB(TypeAdapter(list[Step])))
    # Soft delete: rules and runbook runs reference runbooks with ON DELETE RESTRICT. NULL while active.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, sort_order=1)
