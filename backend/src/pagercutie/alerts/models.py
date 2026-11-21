"""Tables written by the pipeline stages: alerts, deliveries, runbook runs and step runs."""

import uuid
from datetime import datetime

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, false, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pagercutie.alerts.schemas import (
    AlertField,
    AlertStatus,
    DeliveryStatus,
    Resolution,
    StepStatus,
)
from pagercutie.core.enums import Channel, Severity
from pagercutie.core.models import Base, CreatedAtMixin, IdMixin, PydanticJSONB, str_enum
from pagercutie.rules.schemas import Colour
from pagercutie.runbooks.steps import Step

UNRESOLVED = "status <> 'resolved'"


class Alert(IdMixin, Base, kw_only=True):
    """An alert, created by the dedup stage from the first match of a fingerprint (SPEC §9)."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index(
            "uq_alerts_fingerprint_unresolved",
            "fingerprint",
            unique=True,
            postgresql_where=text(UNRESOLVED),
        ),
        Index("ix_alerts_escalated_team_ids", "escalated_team_ids", postgresql_using="gin"),
        # The feed's ORDER BY last_seen_at DESC, id DESC LIMIT n walks this backwards instead of sorting every row.
        Index("ix_alerts_last_seen_at_id", "last_seen_at", "id"),
        CheckConstraint("occurrences >= 1", name="occurrences_positive"),
        CheckConstraint("notifications >= 1", name="notifications_positive"),
        CheckConstraint("status <> 'acknowledged' OR acknowledged_at IS NOT NULL", name="acknowledged_has_time"),
        CheckConstraint(
            "(status = 'resolved') = (resolved_at IS NOT NULL AND resolution IS NOT NULL)", name="resolved_has_time"
        ),
        CheckConstraint("resolved_by IS NULL OR resolution = 'manual'", name="auto_resolution_has_no_user"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rules.id", ondelete="RESTRICT"), index=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[AlertStatus] = mapped_column(str_enum(AlertStatus, "alert_status"))
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "severity"))
    colour: Mapped[Colour] = mapped_column(str_enum(Colour, "colour"))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    fields: Mapped[list[AlertField]] = mapped_column(PydanticJSONB(TypeAdapter(list[AlertField])))
    occurrences: Mapped[int]
    notifications: Mapped[int] = mapped_column(server_default=text("1"), init=False)
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolution: Mapped[Resolution | None] = mapped_column(str_enum(Resolution, "resolution"), default=None)
    escalated_team_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid()))
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)


class Delivery(CreatedAtMixin, Base, kw_only=True):
    """One recipient and channel for one alert (DEL-6)."""

    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_deliveries_undelivered", "created_at", postgresql_where=text("status IN ('pending', 'failed')")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, sort_order=-1)

    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"))
    status: Mapped[DeliveryStatus] = mapped_column(str_enum(DeliveryStatus, "delivery_status"))
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    message: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    traceparent: Mapped[str | None] = mapped_column(Text, default=None)
    digest_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deliveries.id", ondelete="RESTRICT"), default=None)


class RunbookRun(IdMixin, CreatedAtMixin, Base, kw_only=True):
    """The runbook state machine of one alert (SPEC §11.3)."""

    __tablename__ = "runbook_runs"

    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id", ondelete="RESTRICT"), unique=True)
    runbook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runbooks.id", ondelete="RESTRICT"), index=True)
    event: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    # When the last unfinished step finished; set once, by `alerts.runs.advance_run` or `close_run` (ADR-0108).
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    steps: Mapped[list[StepRun]] = relationship(
        order_by="StepRun.index", cascade="all, delete-orphan", lazy="raise", default_factory=list
    )


class StepRun(Base, kw_only=True):
    """One step of a runbook run. Also the executor's job table (`SELECT … FOR UPDATE SKIP LOCKED`, SPEC §11.3)."""

    __tablename__ = "step_runs"
    __table_args__ = (
        CheckConstraint("index >= 0", name="index_non_negative"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("failures >= 0", name="failures_non_negative"),
        CheckConstraint("errors >= 0", name="errors_non_negative"),
        CheckConstraint("occurrences_at_run IS NULL OR occurrences_at_run >= 1", name="occurrences_at_run_positive"),
        Index("ix_step_runs_run_at", "run_at", postgresql_where=text("run_at IS NOT NULL")),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runbook_runs.id", ondelete="CASCADE"), primary_key=True, init=False
    )
    index: Mapped[int] = mapped_column(primary_key=True)
    step: Mapped[Step] = mapped_column(PydanticJSONB(TypeAdapter(Step)))
    status: Mapped[StepStatus] = mapped_column(str_enum(StepStatus, "step_status"))
    attempts: Mapped[int] = mapped_column(default=0)
    failures: Mapped[int] = mapped_column(default=0)
    result: Mapped[str | None] = mapped_column(Text, default=None)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    guard_answered: Mapped[bool] = mapped_column(default=False, server_default=false())
    approved: Mapped[bool] = mapped_column(default=False, server_default=false())
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set by a claim; until it passes no other replica claims the step, and an outcome is written only while it holds
    # the claimed value (ADR-0008, ADR-0108).
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Idempotency key of the action attempt in progress or last made, sent to the integration (ADR-0106).
    attempt_key: Mapped[uuid.UUID | None] = mapped_column(default=None)
    # When that attempt started (`running`); a repeat seen no later than this does not fail a retry (SPEC §11.4).
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Claims that ended without an outcome (an exception or a lost replica); the step fails at the bound (ADR-0106).
    errors: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    # W3C trace context of the ingest request that started the run, so step spans link to it (SPEC §13).
    traceparent: Mapped[str | None] = mapped_column(Text, default=None)
    occurrences_at_run: Mapped[int | None] = mapped_column(default=None)
