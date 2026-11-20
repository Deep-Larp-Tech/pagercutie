import uuid

from pydantic import Field

from larper.core.schemas import InputModel, ReadModel, ShortText
from larper.persons.elo import DEFAULT_ELO


class PersonCreate(InputModel):
    first_name: ShortText
    last_name: ShortText
    larp_elo: int = Field(default=DEFAULT_ELO, strict=True, ge=0, le=5000)


class PersonUpdate(InputModel):
    """Elo is not editable: it only moves through LARPing events. Omitted or null fields stay unchanged."""

    first_name: ShortText | None = None
    last_name: ShortText | None = None


class PersonRead(ReadModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    larp_elo: int
