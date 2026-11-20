import uuid
from typing import Any

from pydantic import Field

from pagercutie.core.schemas import ReadModel, UtcDatetime


class AuditEntryRead(ReadModel):
    id: uuid.UUID
    at: UtcDatetime
    actor_user_id: uuid.UUID | None = Field(description="null: done by the system")
    action: str = Field(examples=["alert.acknowledged", "step.approved", "rule.updated"])
    entity_type: str = Field(examples=["alert", "rule", "team"])
    entity_id: uuid.UUID
    team_id: uuid.UUID | None
    data: dict[str, Any]
