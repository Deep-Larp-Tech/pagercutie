import uuid
from enum import StrEnum

from pydantic import EmailStr

from pagercutie.core.schemas import InputModel, PhoneNumber, ReadModel, ShortText, TimeZone, UtcDatetime


class GlobalRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class UserCreate(InputModel):
    email: EmailStr
    display_name: ShortText
    phone: PhoneNumber | None = None
    timezone: TimeZone = "UTC"
    role: GlobalRole = GlobalRole.USER


class UserUpdate(InputModel):
    """Omitted or null fields stay unchanged. Only admins may change `role`."""

    display_name: ShortText | None = None
    phone: PhoneNumber | None = None
    timezone: TimeZone | None = None
    role: GlobalRole | None = None


class UserRead(ReadModel):
    id: uuid.UUID
    email: str
    display_name: str
    phone: str | None
    timezone: str
    role: GlobalRole
    created_at: UtcDatetime
