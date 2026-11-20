from datetime import datetime

from pydantic import TypeAdapter
from sqlalchemy import CheckConstraint, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from pagercutie.core.models import Base, CreatedAtMixin, IdMixin, PydanticJSONB, str_enum
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.users.schemas import GlobalRole


class User(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Login looks users up by email; the service lowercases it so the unique index is case-insensitive.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        # Unique among active users only, so a soft-deleted user's email can be reused.
        Index("ix_users_email", "email", unique=True, postgresql_where=text("deleted_at IS NULL")),
    )

    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(16))
    timezone: Mapped[str] = mapped_column(String(64))
    role: Mapped[GlobalRole] = mapped_column(str_enum(GlobalRole, "global_role"))
    channel_preferences: Mapped[ChannelPreferences] = mapped_column(
        PydanticJSONB(TypeAdapter(ChannelPreferences)), default=ChannelPreferences
    )
    # Soft delete: set when the user is deleted, NULL while active.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), sort_order=1)
