"""Audit log."""

import uuid
from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import DateTime, Index, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.audit.schemas import AuditAction, AuditEntityType
from pagercutie.core.models import Base, IdMixin, str_enum


class AuditEntry(IdMixin, Base, kw_only=True):
    """Who did what to which entity (RUN-5). Append-only, without foreign keys, so it outlives the rows it names."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_actor_at", "actor_user_id", "at"),
        Index("ix_audit_log_action_at", "action", "at"),
    )

    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, init=False)
    # null: done by the system. Required on purpose: with a default, a forgotten argument would silently
    # attribute the action to the system.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    action: Mapped[AuditAction] = mapped_column(str_enum(AuditAction, "audit_action"))
    entity_type: Mapped[AuditEntityType] = mapped_column(str_enum(AuditEntityType, "audit_entity_type"))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid())
    team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True, default=None)
    data: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
