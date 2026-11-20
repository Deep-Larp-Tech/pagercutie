import uuid
from typing import Annotated

from pydantic import Field

from larper.core.schemas import InputModel, ReadModel, ShortText

# strict: JSON `true` or `4.5` is not a difficulty (lax mode would coerce booleans to 1).
Difficulty = Annotated[int, Field(strict=True, ge=1, le=10)]


class SkillCreate(InputModel):
    name: ShortText
    difficulty: Difficulty


class SkillUpdate(InputModel):
    """Changing difficulty does not recompute Elo of past events. Omitted or null fields stay unchanged."""

    name: ShortText | None = None
    difficulty: Difficulty | None = None


class SkillRead(ReadModel):
    id: uuid.UUID
    name: str
    difficulty: int
