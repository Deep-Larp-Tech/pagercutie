from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from pagercutie.core.schemas import InputModel, LongText, ReadModel, ShortText, UtcDatetime
from pagercutie.events.schemas import Believability
from pagercutie.skills.schemas import Difficulty


class ImportFormat(StrEnum):
    JSON = "json"
    CSV = "csv"


class LarpEventImportRow(InputModel):
    """One row of the import file: JSON array of objects, or CSV with these names as the header."""

    first_name: ShortText
    last_name: ShortText
    skill_name: ShortText
    skill_difficulty: Difficulty
    occurred_at: UtcDatetime
    believability: Believability
    description: LongText
    location: ShortText | None = None

    @field_validator("location", mode="before")
    @classmethod
    def _empty_location_is_none(cls, value: object) -> object:
        # CSV has no null, an empty cell means "no location".
        return None if value == "" else value


class ImportSummaryRead(ReadModel):
    persons_created: int
    skills_created: int
    events_created: int


class ImportPhase(StrEnum):
    PARSING = "parsing"
    VALIDATING = "validating"
    WRITING = "writing"


class ImportProgress(BaseModel):
    """`processed` of `total` rows done in this phase; `total` is unknown until the file is parsed."""

    type: Literal["progress"] = "progress"
    phase: ImportPhase
    processed: int = 0
    total: int | None = None


class ImportCompleted(BaseModel):
    """Sent only after the import is committed."""

    type: Literal["completed"] = "completed"
    summary: ImportSummaryRead


class ImportErrorDetail(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ImportFailed(BaseModel):
    """Nothing was imported. `status` and `detail` match the HTTP error the same failure gets elsewhere."""

    type: Literal["failed"] = "failed"
    status: int
    detail: str | list[ImportErrorDetail]


ImportEvent = Annotated[ImportProgress | ImportCompleted | ImportFailed, Field(discriminator="type")]
