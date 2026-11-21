"""Messages passed between pipeline stages inside one replica (SPEC §5.1). Frozen: a stage never edits its input."""

import uuid

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from pagercutie.core.enums import Severity
from pagercutie.core.schemas import UtcDatetime
from pagercutie.rules.schemas import RuleRead
from pagercutie.sources.schemas import SourceType


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)


class RawEvent(Message):
    """One event as a source adapter received it: an HTTP body or one WebSocket message."""

    source_slug: str
    source_type: SourceType = Field(description="Type of the adapter that received it; must match the source's type")
    token: str | None = Field(description="Bearer token sent by the producer; null when none was sent")
    content_type: str = Field(description="Media type of `body`, e.g. application/json")
    body: bytes


class Event(Message):
    """The normalised event every rule is evaluated against (SPEC §4.2)."""

    event_id: uuid.UUID = Field(description="UUIDv7 assigned by ingest")
    source: str = Field(description="Source slug, e.g. payments-webhook")
    source_id: uuid.UUID
    team_id: uuid.UUID = Field(description="The source's owning team")
    schema_id: uuid.UUID = Field(description="Resolved by ingest (SPEC §7)")
    severity: Severity = Field(description="Normalised through the source's severity mapping (SPEC §8.1)")
    received_at: UtcDatetime = Field(description="Ingest time; basis for end-to-end latency")
    payload: dict[str, JsonValue] = Field(description="Event body as JSON, whatever the original wire format was")


class Match(Message):
    """One event that satisfied one rule. `rule` is the rule as evaluated, so later stages read no rule rows."""

    event: Event
    rule: RuleRead
    fingerprint: str = Field(description="Hex SHA-256 of the rule ID and its dedup field values (SPEC §9)")


class Opened(Message):
    """The match created a new alert: route it and start its runbook run."""

    alert_id: uuid.UUID
    match: Match


class Renotified(Message):
    """The match opened a new dedup window on an alert that is still not resolved: route it again."""

    alert_id: uuid.UUID
    match: Match
    notification_seq: int = Field(ge=2, description="1 is the alert's first notification")


class Repeated(Message):
    """The match only counted as one more occurrence of an existing alert."""

    alert_id: uuid.UUID
    match: Match


type DedupOutcome = Opened | Renotified | Repeated


class IngestResult(Message):
    """What ingest answers with `202` once every outcome is committed."""

    event_id: uuid.UUID
    matches: int = Field(ge=0, description="Rules the event matched")
