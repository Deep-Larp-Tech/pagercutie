"""Messages passed between pipeline stages inside one replica (SPEC §5.1). Frozen: a stage never edits its input."""

import uuid

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from pagercutie.core.enums import Severity
from pagercutie.core.schemas import UtcDatetime
from pagercutie.rules import evaluator
from pagercutie.rules.schemas import RuleRead
from pagercutie.sources.service import IngestSource


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)


class RawEvent(Message):
    """One event as a source adapter received it, from a source the adapter authenticated (SPEC §6)."""

    source: IngestSource = Field(description="The enabled source whose current token the producer sent")
    body: bytes = Field(description="The event as JSON text: an HTTP body or one WebSocket message (SPEC §4.2)")


class Event(Message):
    """The normalised event every rule is evaluated against (SPEC §4.2)."""

    event_id: uuid.UUID = Field(description="UUIDv7 assigned by ingest")
    source: str = Field(description="Source slug, e.g. payments-webhook")
    source_id: uuid.UUID
    team_id: uuid.UUID = Field(description="The source's owning team")
    schema_id: uuid.UUID = Field(description="Resolved by ingest (SPEC §7)")
    schema_name: str = Field(description="Name of the resolved event schema (SPEC §7)")
    severity: Severity = Field(description="Normalised through the source's severity mapping (SPEC §8.1)")
    received_at: UtcDatetime = Field(description="Ingest time; basis for end-to-end latency")
    payload: dict[str, JsonValue] = Field(description="Event body as JSON, whatever the original wire format was")

    def view(self) -> evaluator.EventView:
        """The event as rule conditions, fingerprints and templates see it (SPEC §8.1)."""
        return evaluator.event_view(
            source=self.source,
            schema=self.schema_name,
            schema_id=self.schema_id,
            severity=self.severity,
            payload=self.payload,
        )


class Match(Message):
    """One event that satisfied one rule. `rule` is the rule as evaluated, so later stages read no rule rows."""

    event: Event
    rule: RuleRead
    fingerprint: str = Field(description="Hex SHA-256 of the rule ID and its dedup field values (SPEC §9)")


class Opened(Message):
    """The match created a new alert: route it and start its runbook run.

    Carries the alert row's columns that routing and the executor need, so neither reads the uncommitted row.
    """

    alert_id: uuid.UUID
    match: Match
    team_id: uuid.UUID | None = Field(description="The alert's team; null for a personal rule's alert")
    severity: Severity = Field(description="The alert's severity, from the rule's presentation")
    title: str = Field(description="The alert's rendered title")
    body: str | None = Field(description="The alert's rendered body; null when the rule has none")


class Renotified(Message):
    """The alert is unresolved and last notified at least a dedup window before this match: route it again.

    `team_id`, `severity`, `title` and `body` are the alert row's, as rendered when the alert opened.
    """

    alert_id: uuid.UUID
    match: Match
    team_id: uuid.UUID | None = Field(description="The alert's team; null for a personal rule's alert")
    severity: Severity = Field(description="The alert's severity, from the rule's presentation")
    title: str = Field(description="The alert's rendered title")
    body: str | None = Field(description="The alert's rendered body; null when the rule has none")
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
