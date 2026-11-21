"""Tables written by the pipeline stages: alerts, deliveries, runbook runs and step runs."""

import uuid
from datetime import datetime

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pagercutie.alerts.schemas import (
    AlertField,
    AlertStatus,
    DeliveryStatus,
    Resolution,
    StepDecisionKind,
    StepStatus,
)
from pagercutie.core.enums import Channel, Severity
from pagercutie.core.models import Base, CreatedAtMixin, IdMixin, PydanticJSONB, str_enum
from pagercutie.rules.schemas import Colour
from pagercutie.runbooks.steps import Step

# Predicate of the partial unique index on the fingerprint; the dedup upsert names it as its conflict target.
UNRESOLVED = "status <> 'resolved'"


class Alert(IdMixin, Base, kw_only=True):
    """An alert, created by the dedup stage from the first match of a fingerprint (SPEC §9)."""

    __tablename__ = "alerts"
    __table_args__ = (
        # Makes the dedup upsert idempotent (ADR-0017, ADR-0043).
        Index(
            "uq_alerts_fingerprint_unresolved",
            "fingerprint",
            unique=True,
            postgresql_where=text(UNRESOLVED),
        ),
        # Team feeds also show alerts escalated to the team.
        Index("ix_alerts_escalated_team_ids", "escalated_team_ids", postgresql_using="gin"),
        CheckConstraint("occurrences >= 1", name="occurrences_positive"),
        CheckConstraint("notifications >= 1", name="notifications_positive"),
        CheckConstraint("status <> 'acknowledged' OR acknowledged_at IS NOT NULL", name="acknowledged_has_time"),
        CheckConstraint(
            "(status = 'resolved') = (resolved_at IS NOT NULL AND resolution IS NOT NULL)", name="resolved_has_time"
        ),
        # `auto` is the pipeline closing the alert (RUN-5), so nobody resolved it.
        CheckConstraint("resolved_by IS NULL OR resolution = 'manual'", name="auto_resolution_has_no_user"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rules.id", ondelete="RESTRICT"), index=True)
    # The rule's owning team, copied for the feed query; null for personal rules. Required on purpose: a forgotten
    # argument would hide a team alert from the team feed.
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[AlertStatus] = mapped_column(str_enum(AlertStatus, "alert_status"))
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "severity"))
    colour: Mapped[Colour] = mapped_column(str_enum(Colour, "colour"))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    fields: Mapped[list[AlertField]] = mapped_column(PydanticJSONB(TypeAdapter(list[AlertField])))
    occurrences: Mapped[int]
    # Notification rounds: 1 when the alert opens, one more per `Renotified`; part of the delivery IDs (SPEC §5.4).
    notifications: Mapped[int] = mapped_column(server_default=text("1"), init=False)
    # `received_at` of the event behind the last notification round; a match renotifies once it is a dedup window old.
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolution: Mapped[Resolution | None] = mapped_column(str_enum(Resolution, "resolution"), default=None)
    escalated_team_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid()))
    # Payload of the first event.
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)


class Delivery(CreatedAtMixin, Base, kw_only=True):
    """One recipient and channel for one alert (DEL-6)."""

    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        # The claim query takes pending and failed rows oldest first (DEL-5, SPEC §10). `created_at` serves its
        # ORDER BY ... LIMIT; the retry_at and lease_until conditions filter the few rows the predicate keeps.
        Index("ix_deliveries_undelivered", "created_at", postgresql_where=text("status IN ('pending', 'failed')")),
    )

    # No default: routing sets a deterministic ID, so routing an outcome twice inserts nothing new (SPEC §5.4).
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, sort_order=-1)

    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"))
    status: Mapped[DeliveryStatus] = mapped_column(str_enum(DeliveryStatus, "delivery_status"))
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    message: Mapped[str] = mapped_column(Text)
    # When ingest received the event behind this delivery; the start of `end_to_end_latency_seconds` (SPEC §13).
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set when a dispatcher claims the row; another replica may claim it again after it passes (SPEC §10).
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # W3C trace context of the ingest request, so the send span links to it (SPEC §13).
    traceparent: Mapped[str | None] = mapped_column(Text, default=None)
    # The digest delivery that carried this throttled delivery instead of a message of its own (SPEC §9).
    digest_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deliveries.id", ondelete="RESTRICT"), default=None)


class RunbookRun(IdMixin, CreatedAtMixin, Base, kw_only=True):
    """The runbook state machine of one alert (SPEC §11.3)."""

    __tablename__ = "runbook_runs"

    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id", ondelete="RESTRICT"), unique=True)
    runbook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runbooks.id", ondelete="RESTRICT"), index=True)
    # The alert's first event as `rules.evaluator.event_view` builds it, so step templates render with
    # `template_resolver` (SPEC §11.2).
    event: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)

    # lazy="raise": an implicit load fails under asyncio, so callers load steps with selectinload.
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
        CheckConstraint("occurrences_at_run IS NULL OR occurrences_at_run >= 1", name="occurrences_at_run_positive"),
        Index("ix_step_runs_run_at", "run_at", postgresql_where=text("run_at IS NOT NULL")),
    )

    # Set from `RunbookRun.steps` on flush.
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runbook_runs.id", ondelete="CASCADE"), primary_key=True, init=False
    )
    index: Mapped[int] = mapped_column(primary_key=True)
    # Copied when the run starts, so editing the runbook leaves runs in progress unchanged.
    step: Mapped[Step] = mapped_column(PydanticJSONB(TypeAdapter(Step)))
    status: Mapped[StepStatus] = mapped_column(str_enum(StepStatus, "step_status"))
    attempts: Mapped[int] = mapped_column(default=0)
    failures: Mapped[int] = mapped_column(default=0)
    result: Mapped[str | None] = mapped_column(Text, default=None)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # When the executor should pick the step up next; null while it waits for a person or has finished.
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # The latest human decision, recorded by the decision endpoint and applied by the executor (SPEC §11.3).
    decision: Mapped[StepDecisionKind | None] = mapped_column(str_enum(StepDecisionKind, "step_decision"), default=None)
    # `alerts.occurrences` when a `retry_workflow` step last ran: the baseline for detecting a failed retry (ADR-0020).
    occurrences_at_run: Mapped[int | None] = mapped_column(default=None)
