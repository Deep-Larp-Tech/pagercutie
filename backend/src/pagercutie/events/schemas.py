import uuid
from datetime import datetime
from typing import Annotated

from pydantic import Field

from pagercutie.core.schemas import InputModel, LongText, Pagination, ReadModel, ShortText, UtcDatetime
from pagercutie.persons.schemas import PersonRead
from pagercutie.skills.schemas import SkillRead

Believability = Annotated[int, Field(strict=True, ge=1, le=10)]


class LarpEventCreate(InputModel):
    person_id: uuid.UUID
    skill_id: uuid.UUID
    occurred_at: UtcDatetime
    believability: Believability
    description: LongText
    location: ShortText | None = None


class LarpEventQuery(Pagination):
    person_id: uuid.UUID | None = None
    skill_id: uuid.UUID | None = None


class LarpEventRead(ReadModel):
    id: uuid.UUID
    occurred_at: datetime
    believability: int
    description: str
    location: str | None
    elo_delta: int
    person: PersonRead
    skill: SkillRead
