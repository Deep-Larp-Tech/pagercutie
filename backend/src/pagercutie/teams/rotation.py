"""On-call calculation for a team's weekly rotation (DOMAIN.md §5)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pagercutie.core.enums import Weekday
from pagercutie.teams.models import Rotation

_WEEK = timedelta(days=7)
_WEEKDAYS = tuple(Weekday)


@dataclass(frozen=True)
class OnCall:
    """The user on call and the UTC instant their shift ends."""

    user_id: uuid.UUID
    until: datetime


def on_call_at(rotation: Rotation, now: datetime) -> OnCall | None:
    """The member on call at `now` (`None` without members); `rotation.members` must be loaded and ordered.

    `members[0]` is on call from `started_at` until the first handoff after it; every handoff passes the shift to the
    next member, wrapping around. A handoff is the wall-clock `handoff_day` and `handoff_time` in `rotation.timezone`,
    so a time inside a DST gap lands after the gap and an ambiguous time takes its first occurrence. Before
    `started_at`, `members[0]` is on call until that first handoff. `now` must be timezone-aware (`ValueError`
    otherwise).
    """
    if now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    members = rotation.members
    if not members:
        return None
    zone = ZoneInfo(rotation.timezone)
    first = _first_handoff_date_after(
        rotation.started_at, _WEEKDAYS.index(rotation.handoff_day), rotation.handoff_time, zone
    )

    def handoff(weeks_after_first: int) -> datetime:
        return _handoff(first + weeks_after_first * _WEEK, rotation.handoff_time, zone)

    if now < handoff(0):
        return OnCall(members[0].user_id, handoff(0))

    elapsed = max((now.astimezone(zone).date() - first).days // 7, 0)
    while handoff(elapsed + 1) <= now:
        elapsed += 1
    while handoff(elapsed) > now:
        elapsed -= 1
    return OnCall(members[(elapsed + 1) % len(members)].user_id, handoff(elapsed + 1))


def _handoff(day: date, at: time, zone: ZoneInfo) -> datetime:
    """The UTC instant of the wall-clock `at` on `day` in `zone`."""
    return datetime.combine(day, at, tzinfo=zone).astimezone(UTC)


def _first_handoff_date_after(instant: datetime, weekday: int, at: time, zone: ZoneInfo) -> date:
    """The local date of the first handoff strictly after `instant`."""
    local_date = instant.astimezone(zone).date()
    candidate = local_date + timedelta(days=(weekday - local_date.weekday()) % 7)
    if _handoff(candidate, at, zone) <= instant:
        candidate += _WEEK
    return candidate
