"""DTO building blocks shared by every entity."""

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

# Postgres text cannot hold NUL bytes
_NO_NUL = r"^[^\x00]*$"

ShortText = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=_NO_NUL)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=_NO_NUL)]


def _to_utc(value: datetime) -> datetime:
    try:
        return value.astimezone(UTC)
    except OverflowError as e:  # e.g. 0001-01-01T00:00+01:00 has no UTC equivalent
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
