from typing import Literal

from larper.core.schemas import ReadModel


class HealthRead(ReadModel):
    status: Literal["ok"]
    database: Literal["ok"]
