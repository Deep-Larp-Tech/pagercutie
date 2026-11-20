from typing import Literal

from pagercutie.core.schemas import ReadModel


class HealthRead(ReadModel):
    status: Literal["ok"]
    database: Literal["ok"]
