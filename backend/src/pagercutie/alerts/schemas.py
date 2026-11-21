import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, JsonValue

from pagercutie.core.enums import Channel, Severity
from pagercutie.core.schemas import InputModel, LongText, ReadModel, UtcDatetime
from pagercutie.rules.schemas import Colour
from pagercutie.runbooks.steps import Step


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class Resolution(StrEnum):
    MANUAL = "manual"
    AUTO = "auto"


class AlertField(ReadModel):
    path: str
    value: JsonValue


class AlertRead(ReadModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    team_id: uuid.UUID | None = Field(description="Owning team; null for personal rules")
    fingerprint: str
    status: AlertStatus
    severity: Severity
    colour: Colour
    title: str
    body: str | None
    fields: list[AlertField]
    occurrences: int
    first_seen_at: UtcDatetime
    last_seen_at: UtcDatetime
    acknowledged_by: uuid.UUID | None
    acknowledged_at: UtcDatetime | None
    resolved_by: uuid.UUID | None = Field(description="null with `resolution: auto`")
    resolved_at: UtcDatetime | None
    resolution: Resolution | None
    escalated_team_ids: list[uuid.UUID]
    payload: dict[str, Any] = Field(description="Payload of the first event")


class ResolveRequest(InputModel):
    note: LongText | None = None


AlertEventType = Literal["alert.created", "alert.updated"]


class AlertEvent(ReadModel):
    """One message of the live feed (`GET /alerts/stream`)."""

    type: AlertEventType
    alert: AlertRead


class DeliveryStatus(StrEnum):
    """Where a delivery is in its lifecycle (DOMAIN.md §6); `sent`, `undeliverable` and `cancelled` are terminal."""

    PENDING = "pending"
    SENT = "sent"
    # The last attempt failed and another is scheduled (DEL-5).
    FAILED = "failed"
    # Failed permanently, e.g. the user has no phone number; never retried. A fallback channel may follow (ADR-0110).
    UNDELIVERABLE = "undeliverable"
    # The alert was resolved before the delivery was sent (ADR-0110).
    CANCELLED = "cancelled"


class DeliveryRead(ReadModel):
    id: uuid.UUID
    alert_id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    status: DeliveryStatus
    attempts: int
    last_error: str | None
    message: str = Field(description="What was sent, as rendered for the channel")
    created_at: UtcDatetime
    sent_at: UtcDatetime | None


class StepStatus(StrEnum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_ANSWER = "awaiting_answer"
    AWAITING_MANUAL = "awaiting_manual"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepRunRead(ReadModel):
    index: int
    step: Step
    status: StepStatus
    attempts: int
    failures: int
    result: str | None = Field(description="Outcome shown on the alert, e.g. 'HTTP 200 in 35 ms'")
    decided_by: uuid.UUID | None
    decided_at: UtcDatetime | None


class RunbookRunRead(ReadModel):
    id: uuid.UUID
    alert_id: uuid.UUID
    runbook_id: uuid.UUID
    steps: list[StepRunRead]


class StepDecisionKind(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    YES = "yes"
    NO = "no"
    DONE = "done"


class StepDecision(InputModel):
    """`approve`/`reject` for awaiting_approval, `yes`/`no` for awaiting_answer, `done` for awaiting_manual."""

    decision: StepDecisionKind
    note: LongText | None = None
