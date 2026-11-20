import uuid
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field

from pagercutie.core.enums import Channel, Severity
from pagercutie.core.schemas import FieldPath, InputModel, LongText, ReadModel, ShortText, Template, UtcDatetime
from pagercutie.rules.ast import Condition


class TeamOwner(InputModel):
    type: Literal["team"]
    team_id: uuid.UUID


class UserOwner(InputModel):
    """A personal rule: only its user is notified, and only for events from sources their teams can see."""

    type: Literal["user"]
    user_id: uuid.UUID


type Owner = Annotated[TeamOwner | UserOwner, Field(discriminator="type")]


class UserRecipient(InputModel):
    type: Literal["user"]
    user_id: uuid.UUID


class TeamRecipient(InputModel):
    """All leads and members of the team."""

    type: Literal["team"]
    team_id: uuid.UUID


class OnCallRecipient(InputModel):
    """The team's current on-call user."""

    type: Literal["on_call"]
    team_id: uuid.UUID


type Recipient = Annotated[UserRecipient | TeamRecipient | OnCallRecipient, Field(discriminator="type")]


class Dedup(InputModel):
    """Matches with the same fingerprint (rule + values of `fields`) within `window_s` are one alert."""

    fields: list[FieldPath] = Field(default_factory=list, max_length=10)
    window_s: int = Field(default=300, ge=1, le=86_400)


class Routing(InputModel):
    recipients: list[Recipient] = Field(min_length=1, max_length=20)
    channels: list[Channel] | None = Field(default=None, description="null: use the recipients' preferences")


class Colour(StrEnum):
    RED = "red"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    GREY = "grey"


class Presentation(InputModel):
    title: Template
    body: Template | None = None
    fields: list[FieldPath] = Field(default_factory=list, max_length=20)
    severity: Severity
    colour: Colour | None = Field(default=None, description="null: derived from severity")


class RuleCreate(InputModel):
    name: ShortText
    description: LongText | None = None
    enabled: bool = True
    owner: Owner
    schema_ids: list[uuid.UUID] = Field(default_factory=list, description="Empty: events of any schema")
    condition: Condition
    dedup: Dedup = Field(default_factory=Dedup)
    routing: Routing
    presentation: Presentation
    runbook_id: uuid.UUID | None = None


class RuleUpdate(InputModel):
    """Omitted fields stay unchanged. `null` clears `description` and `runbook_id`; elsewhere it means unchanged.

    The owner is permanent.
    """

    name: ShortText | None = None
    description: LongText | None = None
    enabled: bool | None = None
    schema_ids: list[uuid.UUID] | None = None
    condition: Condition | None = None
    dedup: Dedup | None = None
    routing: Routing | None = None
    presentation: Presentation | None = None
    runbook_id: uuid.UUID | None = None


class RuleRead(ReadModel):
    id: uuid.UUID
    name: str
    description: str | None
    enabled: bool
    owner: Owner
    schema_ids: list[uuid.UUID]
    condition: Condition
    dedup: Dedup
    routing: Routing
    presentation: Presentation
    runbook_id: uuid.UUID | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class RuleTestRequest(InputModel):
    """A sample event for the builder's "does it match?" preview."""

    condition: Condition
    payload: dict[str, Any]
    source: str = "test"
    schema_id: uuid.UUID | None = None
    severity: Severity = Severity.INFO


class RuleTestResult(ReadModel):
    matched: bool
    title: str | None = Field(default=None, description="Rendered title when a presentation was sent")
