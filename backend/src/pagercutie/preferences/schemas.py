from datetime import time

from pydantic import Field

from pagercutie.core.enums import Channel, Severity, Weekday
from pagercutie.core.schemas import InputModel


class TimeWindow(InputModel):
    """Local time in the owner's time zone. `end` before `start` crosses midnight."""

    days: list[Weekday] = Field(default_factory=lambda: list(Weekday), min_length=1)
    start: time
    end: time


class ChannelRule(InputModel):
    min_severity: Severity
    channels: list[Channel] = Field(min_length=1)
    window: TimeWindow | None = None


class ChannelPreferences(InputModel):
    """The first rule matching the alert's severity and the current local time wins; no match → UI only."""

    rules: list[ChannelRule] = Field(default_factory=list, max_length=20)
