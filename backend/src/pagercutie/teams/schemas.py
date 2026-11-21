import uuid
from datetime import time
from enum import StrEnum

from pydantic import Field

from pagercutie.core.enums import Weekday
from pagercutie.core.schemas import InputModel, LongText, ReadModel, ShortText, Slug, TimeZone, UtcDatetime
from pagercutie.users.schemas import UserRead


class TeamRole(StrEnum):
    LEAD = "lead"
    MEMBER = "member"
    VIEWER = "viewer"


class TeamCreate(InputModel):
    slug: Slug
    name: ShortText
    description: LongText | None = None


class TeamUpdate(InputModel):
    """Omitted or null fields stay unchanged. The slug is permanent."""

    name: ShortText | None = None
    description: LongText | None = None


class TeamRead(ReadModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    created_at: UtcDatetime


class MembershipSet(InputModel):
    role: TeamRole


class MemberRead(ReadModel):
    user: UserRead
    role: TeamRole


class Rotation(InputModel):
    """Weekly rotation: `user_ids[0]` first, the next user takes over at every handoff, wrapping around."""

    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    handoff_day: Weekday = Weekday.MON
    handoff_time: time = time(9, 0)
    timezone: TimeZone = "UTC"


class OnCallRead(ReadModel):
    team_id: uuid.UUID
    user: UserRead | None = Field(
        description="null when the team has no rotation, the rotation has no members, or the on-call user is deleted"
    )
    until: UtcDatetime | None
