from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from pagercutie.core.enums import Channel, Severity, Weekday
from pagercutie.preferences.resolution import resolve_channels
from pagercutie.preferences.schemas import ChannelPreferences, ChannelRule, TimeWindow

PRAGUE = "Europe/Prague"
ALL_DAYS = list(Weekday)

ANNA = ChannelPreferences(
    rules=[
        ChannelRule(
            min_severity=Severity.CRITICAL,
            channels=[Channel.SMS],
            window=TimeWindow(days=ALL_DAYS, start=time(8), end=time(20)),
        ),
        ChannelRule(min_severity=Severity.CRITICAL, channels=[Channel.EMAIL]),
    ]
)


def local(year: int, month: int, day: int, hour: int, minute: int = 0, zone: str = PRAGUE) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(zone))


def window_rule(start: time, end: time, days: list[Weekday] | None = None) -> ChannelPreferences:
    window = TimeWindow(days=days or ALL_DAYS, start=start, end=end)
    return ChannelPreferences(rules=[ChannelRule(min_severity=Severity.DEBUG, channels=[Channel.SMS], window=window)])


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (7, 59, [Channel.EMAIL]),
        (8, 0, [Channel.SMS]),
        (19, 59, [Channel.SMS]),
        (20, 0, [Channel.EMAIL]),
    ],
)
def test_anna_gets_sms_from_08_00_until_20_00_local_time(hour: int, minute: int, expected: list[Channel]) -> None:
    assert resolve_channels(ANNA, Severity.CRITICAL, local(2026, 6, 10, hour, minute), PRAGUE) == expected


def test_the_instant_is_converted_to_the_zone() -> None:
    now = datetime(2026, 6, 10, 6, 0, tzinfo=UTC)  # 08:00 in Prague (UTC+2)
    assert resolve_channels(ANNA, Severity.CRITICAL, now, PRAGUE) == [Channel.SMS]
    assert resolve_channels(ANNA, Severity.CRITICAL, now, "UTC") == [Channel.EMAIL]


def test_a_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_channels(ANNA, Severity.CRITICAL, datetime(2026, 6, 10, 8), PRAGUE)


def test_no_match_returns_an_empty_list() -> None:
    assert resolve_channels(ANNA, Severity.WARN, local(2026, 6, 10, 12), PRAGUE) == []
    assert resolve_channels(ChannelPreferences(), Severity.CRITICAL, local(2026, 6, 10, 12), PRAGUE) == []


def test_a_window_miss_falls_through_to_no_match() -> None:
    prefs = window_rule(time(8), time(20))
    assert resolve_channels(prefs, Severity.INFO, local(2026, 6, 10, 21), PRAGUE) == []


def test_severity_is_compared_by_rank_not_alphabetically() -> None:
    prefs = ChannelPreferences(rules=[ChannelRule(min_severity=Severity.WARN, channels=[Channel.PHONE])])
    now = local(2026, 6, 10, 12)
    # Alphabetically "critical" < "warn" and "error" < "warn", but both outrank warn.
    assert resolve_channels(prefs, Severity.CRITICAL, now, PRAGUE) == [Channel.PHONE]
    assert resolve_channels(prefs, Severity.ERROR, now, PRAGUE) == [Channel.PHONE]
    assert resolve_channels(prefs, Severity.WARN, now, PRAGUE) == [Channel.PHONE]
    assert resolve_channels(prefs, Severity.INFO, now, PRAGUE) == []
    assert resolve_channels(prefs, Severity.DEBUG, now, PRAGUE) == []


def test_the_first_matching_rule_wins() -> None:
    prefs = ChannelPreferences(
        rules=[
            ChannelRule(min_severity=Severity.CRITICAL, channels=[Channel.PHONE]),
            ChannelRule(min_severity=Severity.DEBUG, channels=[Channel.EMAIL]),
            ChannelRule(min_severity=Severity.DEBUG, channels=[Channel.SMS]),
        ]
    )
    now = local(2026, 6, 10, 12)
    assert resolve_channels(prefs, Severity.CRITICAL, now, PRAGUE) == [Channel.PHONE]
    assert resolve_channels(prefs, Severity.ERROR, now, PRAGUE) == [Channel.EMAIL]


def test_a_rule_returns_all_its_channels_in_order() -> None:
    prefs = ChannelPreferences(
        rules=[ChannelRule(min_severity=Severity.DEBUG, channels=[Channel.PHONE, Channel.SMS, Channel.EMAIL])]
    )
    assert resolve_channels(prefs, Severity.INFO, local(2026, 6, 10, 12), PRAGUE) == [
        Channel.PHONE,
        Channel.SMS,
        Channel.EMAIL,
    ]


def test_days_restrict_a_same_day_window() -> None:
    prefs = window_rule(time(8), time(20), [Weekday.MON])
    assert resolve_channels(prefs, Severity.INFO, local(2026, 6, 8, 12), PRAGUE) == [Channel.SMS]  # Monday
    assert resolve_channels(prefs, Severity.INFO, local(2026, 6, 9, 12), PRAGUE) == []  # Tuesday


class TestMidnightCrossing:
    NIGHT = window_rule(time(22), time(6), [Weekday.FRI])  # window starts Friday 22:00, ends Saturday 06:00

    @pytest.mark.parametrize(
        ("day", "hour", "minute", "inside"),
        [
            (5, 21, 59, False),  # Friday before start
            (5, 22, 0, True),  # Friday start, inclusive
            (5, 23, 59, True),
            (6, 0, 0, True),  # Saturday after midnight: window started on Friday
            (6, 5, 59, True),
            (6, 6, 0, False),  # Saturday end, exclusive
            (6, 22, 0, False),  # Saturday evening: window would start on Saturday
            (5, 5, 0, False),  # Friday early morning: window would have started Thursday
            (7, 3, 0, False),  # Sunday early morning
        ],
    )
    def test_days_names_the_day_the_window_started(self, day: int, hour: int, minute: int, inside: bool) -> None:
        now = local(2026, 6, day, hour, minute)
        assert resolve_channels(self.NIGHT, Severity.INFO, now, PRAGUE) == ([Channel.SMS] if inside else [])

    def test_the_week_wraps_from_sunday_to_monday(self) -> None:
        prefs = window_rule(time(22), time(6), [Weekday.SUN])
        assert resolve_channels(prefs, Severity.INFO, local(2026, 6, 8, 2), PRAGUE) == [Channel.SMS]  # Monday 02:00


def test_a_window_with_start_equal_to_end_is_empty() -> None:
    prefs = window_rule(time(8), time(8))
    for hour in (0, 7, 8, 9, 20, 23):
        assert resolve_channels(prefs, Severity.INFO, local(2026, 6, 10, hour), PRAGUE) == []


class TestDaylightSavingTime:
    def test_spring_forward_skips_an_hour_of_wall_clock(self) -> None:
        # 2026-03-29: Prague jumps from 02:00 to 03:00. 01:00 UTC is 03:00 CEST.
        prefs = window_rule(time(2), time(4))
        before = datetime(2026, 3, 29, 0, 59, tzinfo=UTC)  # 01:59 CET
        after = datetime(2026, 3, 29, 1, 0, tzinfo=UTC)  # 03:00 CEST
        assert resolve_channels(prefs, Severity.INFO, before, PRAGUE) == []
        assert resolve_channels(prefs, Severity.INFO, after, PRAGUE) == [Channel.SMS]
        assert resolve_channels(prefs, Severity.INFO, datetime(2026, 3, 29, 2, 0, tzinfo=UTC), PRAGUE) == []  # 04:00

    def test_fall_back_repeats_an_hour_of_wall_clock(self) -> None:
        # 2026-10-25: Prague goes from 03:00 CEST back to 02:00 CET, so 02:30 happens twice.
        prefs = window_rule(time(2), time(3))
        first = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # 02:30 CEST
        second = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)  # 02:30 CET
        assert resolve_channels(prefs, Severity.INFO, first, PRAGUE) == [Channel.SMS]
        assert resolve_channels(prefs, Severity.INFO, second, PRAGUE) == [Channel.SMS]
        assert resolve_channels(prefs, Severity.INFO, datetime(2026, 10, 25, 2, 0, tzinfo=UTC), PRAGUE) == []  # 03:00

    def test_anna_boundary_moves_with_the_utc_offset(self) -> None:
        winter = datetime(2026, 1, 14, 7, 0, tzinfo=UTC)  # 08:00 CET
        summer = datetime(2026, 7, 15, 6, 0, tzinfo=UTC)  # 08:00 CEST
        assert resolve_channels(ANNA, Severity.CRITICAL, winter, PRAGUE) == [Channel.SMS]
        assert resolve_channels(ANNA, Severity.CRITICAL, summer, PRAGUE) == [Channel.SMS]
        assert resolve_channels(ANNA, Severity.CRITICAL, winter.replace(minute=59, hour=6), PRAGUE) == [Channel.EMAIL]
        assert resolve_channels(ANNA, Severity.CRITICAL, summer.replace(minute=59, hour=5), PRAGUE) == [Channel.EMAIL]
