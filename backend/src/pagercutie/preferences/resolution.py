"""Choosing delivery channels from channel preferences (DOMAIN.md §5)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pagercutie.core.enums import SEVERITY_ORDER, Channel, Severity, Weekday
from pagercutie.preferences.schemas import ChannelPreferences, TimeWindow

_WEEKDAYS = tuple(Weekday)


def resolve_channels(prefs: ChannelPreferences, severity: Severity, now: datetime, timezone: str) -> list[Channel]:
    """Channels of the first rule matching `severity` and the local time of `now` in `timezone`; `[]` means UI only.

    `now` must be timezone-aware (`ValueError` otherwise). A window includes its `start` and excludes its `end`; an
    `end` before `start` crosses midnight and `days` names the day the window started; `start == end` is an empty
    window that never matches. Windows compare wall-clock times, so on a DST change day a window lasts an hour more
    or less.
    """
    if now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(ZoneInfo(timezone))
    rank = SEVERITY_ORDER[severity]
    for rule in prefs.rules:
        if SEVERITY_ORDER[rule.min_severity] <= rank and (rule.window is None or _contains(rule.window, local)):
            return list(rule.channels)
    return []


def fallback_channels(prefs: ChannelPreferences, severity: Severity) -> list[Channel]:
    """Channels to try, in order, when a delivery to a user failed permanently (ADR-0113).

    The channels of every rule matching `severity`, in rule order and whatever their window, then email, which every
    user has. UI is left out: routing always delivers it, and it does not reach a person who is away.
    """
    rank = SEVERITY_ORDER[severity]
    ordered = [
        channel for rule in prefs.rules if SEVERITY_ORDER[rule.min_severity] <= rank for channel in rule.channels
    ]
    return [channel for channel in dict.fromkeys([*ordered, Channel.EMAIL]) if channel is not Channel.UI]


def _contains(window: TimeWindow, local: datetime) -> bool:
    """Whether the zoned datetime `local` is inside `window`."""
    at = local.time()
    if window.start == window.end:
        return False
    if window.start < window.end:
        return window.start <= at < window.end and _weekday(local) in window.days
    if at >= window.start:
        return _weekday(local) in window.days
    if at < window.end:
        return _weekday(local - timedelta(days=1)) in window.days
    return False


def _weekday(moment: datetime) -> Weekday:
    return _WEEKDAYS[moment.weekday()]
