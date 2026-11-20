import uuid
from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints

from pagercutie.core.schemas import FieldPath, InputModel, ReadModel, ShortText, Slug, UtcDatetime
from pagercutie.rules.ast import Condition, Scalar
from pagercutie.runbooks.steps import Step


class RunbookFormat(StrEnum):
    STRUCTURED = "structured"
    MARKDOWN = "markdown"
    TEXT = "text"
    LINK = "link"


RunbookText = Annotated[str, StringConstraints(min_length=1, max_length=100_000)]


class StructuredRunbook(InputModel):
    """The `structured` format: the brief's YAML document (REQUIREMENTS §6.2), exported as runbook.schema.json."""

    runbook: Slug
    matches: dict[FieldPath, Scalar] = Field(
        default_factory=dict, description="Payload fields that must be equal; becomes an `and` of `eq` conditions"
    )
    steps: list[Step] = Field(min_length=1, max_length=50)


class RunbookCreate(InputModel):
    """The server parses `original` into steps; for `structured`, its `matches:` block also sets `attach`."""

    slug: Slug
    title: ShortText
    team_id: uuid.UUID
    format: RunbookFormat
    original: RunbookText
    attach: Condition | None = Field(default=None, description="When the runbook applies; overrides `matches:`")


class RunbookUpdate(InputModel):
    """Omitted or null fields stay unchanged. Changing `original` re-parses the steps."""

    title: ShortText | None = None
    format: RunbookFormat | None = None
    original: RunbookText | None = None
    attach: Condition | None = None


class RunbookRead(ReadModel):
    id: uuid.UUID
    slug: str
    title: str
    team_id: uuid.UUID
    format: RunbookFormat
    original: str
    attach: Condition | None
    steps: list[Step]
    created_at: UtcDatetime
    updated_at: UtcDatetime


class RunbookParseRequest(InputModel):
    format: RunbookFormat
    original: RunbookText


class RunbookParseResult(ReadModel):
    attach: Condition | None
    steps: list[Step]
    warnings: list[str] = Field(description="Parts that fell back to manual steps or human-answered guards")
