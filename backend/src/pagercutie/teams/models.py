import uuid
from datetime import datetime, time

from pydantic import TypeAdapter
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pagercutie.core.enums import Weekday
from pagercutie.core.models import Base, CreatedAtMixin, IdMixin, PydanticJSONB, str_enum
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.teams.schemas import TeamRole


class Team(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "teams"

    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(2000))
    channel_preferences: Mapped[ChannelPreferences] = mapped_column(
        PydanticJSONB(TypeAdapter(ChannelPreferences)), default=ChannelPreferences
    )


class Membership(Base):
    __tablename__ = "memberships"

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[TeamRole] = mapped_column(str_enum(TeamRole, "team_role"))


class Rotation(Base):
    """A team's weekly on-call rotation (DEL-3). `PUT` replaces it, so `started_at` restarts with `user_ids[0]`."""

    __tablename__ = "rotations"

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    handoff_day: Mapped[Weekday] = mapped_column(str_enum(Weekday, "weekday"))
    handoff_time: Mapped[time] = mapped_column(Time())
    timezone: Mapped[str] = mapped_column(String(64))
    # `user_ids[0]` is on call in the week containing this instant (DOMAIN.md §5).
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # lazy="raise": async code must say what it loads (selectinload) instead of tripping over implicit IO.
    members: Mapped[list[RotationMember]] = relationship(
        order_by="RotationMember.position", cascade="all, delete-orphan", lazy="raise"
    )


class RotationMember(Base):
    __tablename__ = "rotation_members"
    __table_args__ = (CheckConstraint("position >= 0", name="position_non_negative"),)

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rotations.team_id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
