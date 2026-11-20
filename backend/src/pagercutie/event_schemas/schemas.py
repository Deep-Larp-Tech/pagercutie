import uuid
from typing import Any

from pydantic import Field

from pagercutie.core.schemas import InputModel, LongText, ReadModel, Slug, UtcDatetime


class EventSchemaCreate(InputModel):
    """A new schema, or a new version of an existing `name`. Versions are immutable."""

    name: Slug
    version: int = Field(ge=1)
    team_id: uuid.UUID
    description: LongText | None = None
    json_schema: dict[str, Any] = Field(description="JSON Schema draft 2020-12 document")


class EventSchemaRead(ReadModel):
    id: uuid.UUID
    name: str
    version: int
    team_id: uuid.UUID
    description: str | None
    json_schema: dict[str, Any]
    created_at: UtcDatetime


class SchemaValidateRequest(InputModel):
    payload: dict[str, Any]


class ValidationIssue(ReadModel):
    path: str = Field(description="JSON pointer into the payload, e.g. /error/code")
    message: str


class SchemaValidateResult(ReadModel):
    valid: bool
    issues: list[ValidationIssue]
