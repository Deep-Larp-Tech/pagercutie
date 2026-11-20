import uuid
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from pagercutie.core.enums import Severity
from pagercutie.core.schemas import FieldPath, InputModel, ReadModel, ShortText, Slug, UtcDatetime


class SourceType(StrEnum):
    WEBHOOK = "webhook"
    WEBSOCKET = "websocket"
    PROTOBUF = "protobuf"


class FixedSchema(InputModel):
    """Every event of the source follows one schema."""

    mode: Literal["fixed"]
    schema_id: uuid.UUID


class DiscriminatedSchema(InputModel):
    """The value of `field` in the payload picks the schema; unmapped values go to the dead-letter topic."""

    mode: Literal["discriminator"]
    field: FieldPath
    mapping: dict[str, uuid.UUID] = Field(min_length=1)


type SchemaResolution = Annotated[FixedSchema | DiscriminatedSchema, Field(discriminator="mode")]


class SeverityMapping(InputModel):
    """Where the event's severity is and how its values map to ours, e.g. `{"WARNING": "warn"}`."""

    field: FieldPath | None = Field(default=None, description="null: every event gets `default`")
    values: dict[str, Severity] = Field(default_factory=dict)
    default: Severity = Severity.INFO


class SourceCreate(InputModel):
    slug: Slug
    name: ShortText
    type: SourceType
    team_id: uuid.UUID
    schema_resolution: SchemaResolution
    severity: SeverityMapping = Field(default_factory=SeverityMapping)
    enabled: bool = True


class SourceUpdate(InputModel):
    """Omitted or null fields stay unchanged. Slug, type and owner are permanent."""

    name: ShortText | None = None
    schema_resolution: SchemaResolution | None = None
    severity: SeverityMapping | None = None
    enabled: bool | None = None


class SourceRead(ReadModel):
    id: uuid.UUID
    slug: str
    name: str
    type: SourceType
    team_id: uuid.UUID
    schema_resolution: SchemaResolution
    severity: SeverityMapping
    enabled: bool
    ingest_url: str = Field(description="Where producers send events, e.g. /ingest/payments-webhook")
    created_at: UtcDatetime


class SourceTokenRead(ReadModel):
    """Returned only once, when the token is (re)generated."""

    token: str
