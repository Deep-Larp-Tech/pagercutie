"""DTO building blocks shared by every entity."""

from datetime import UTC, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from pagercutie.core.fields import FIELD_PATH_PATTERN
from pagercutie.core.templates import parse

NO_NUL = r"^[^\x00]*$"

ShortText = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=NO_NUL)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=NO_NUL)]

Slug = Annotated[str, StringConstraints(min_length=1, max_length=50, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]

FieldPath = Annotated[str, StringConstraints(max_length=200, pattern=f"^{FIELD_PATH_PATTERN}$")]


def _valid_template(value: str) -> str:
    parse(value)
    return value


Template = Annotated[
    str,
    StringConstraints(min_length=1, max_length=2000, pattern=NO_NUL),
    AfterValidator(_valid_template),
    Field(
        description="Text with {{field.path}} placeholders rendered from the event; a path that does not start with "
        "source, schema, schema_id, severity or payload is read under payload"
    ),
]

PhoneNumber = Annotated[str, StringConstraints(pattern=r"^\+[1-9]\d{6,14}$")]


def _known_time_zone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError(f"unknown time zone {value!r}") from e
    return value


TimeZone = Annotated[str, AfterValidator(_known_time_zone), Field(examples=["Europe/Prague"])]


def _to_utc(value: datetime) -> datetime:
    try:
        return value.astimezone(UTC)
    except OverflowError as e:
        raise ValueError("datetime is out of range") from e


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Pagination(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1_000_000)


class ErrorRead(BaseModel):
    detail: str


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorRead} for code in codes}


def json_error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """For routes whose success response is not JSON: a `model` would be documented with the route's media type."""
    schema = {"$ref": f"#/components/schemas/{ErrorRead.__name__}"}
    return {code: {"content": {"application/json": {"schema": schema}}} for code in codes}
