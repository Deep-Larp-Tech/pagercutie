import uuid
from datetime import UTC, datetime, time, timedelta

import pytest

from pagercutie.core.enums import Weekday
from pagercutie.teams.models import Rotation, RotationMember
from pagercutie.teams.rotation import OnCall, on_call_at

PRAGUE = "Europe/Prague"
ANNA, BEN, CARA = (uuid.UUID(int=i) for i in (1, 2, 3))


def make_rotation(
    user_ids: list[uuid.UUID],
    started_at: datetime,
    handoff_day: Weekday = Weekday.MON,
    handoff_time: time = time(9),
    timezone: str = PRAGUE,
) -> Rotation:
    rotation = Rotation(
        team_id=uuid.UUID(int=99),
        handoff_day=handoff_day,
        handoff_time=handoff_time,
        timezone=timezone,
        members=[RotationMember(user_id=user_id, position=position) for position, user_id in enumerate(user_ids)],
    )
    rotation.started_at = started_at
    return rotation


def shift_at(rotation: Rotation, now: datetime) -> OnCall:
    result = on_call_at(rotation, now)
    assert result is not None
    return result


# Wednesday 2026-03-04 12:00 UTC. Handoffs are Mondays 09:00 Prague: 03-09, 03-16, 03-23 (CET, 08:00 UTC), then
# 03-30 (CEST, 07:00 UTC) because DST starts on 03-29.
STARTED = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def rotation() -> Rotation:
    return make_rotation([ANNA, BEN, CARA], STARTED)


def test_no_members_means_nobody_on_call() -> None:
    assert on_call_at(make_rotation([], STARTED), STARTED) is None


def test_a_naive_now_is_rejected(rotation: Rotation) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        on_call_at(rotation, datetime(2026, 3, 5, 12))


def test_the_first_member_is_on_call_until_the_first_handoff(rotation: Rotation) -> None:
    expected = OnCall(ANNA, datetime(2026, 3, 9, 8, 0, tzinfo=UTC))
    assert on_call_at(rotation, STARTED) == expected
    assert on_call_at(rotation, datetime(2026, 3, 9, 7, 59, 59, tzinfo=UTC)) == expected


def test_the_next_member_takes_over_at_the_handoff_instant(rotation: Rotation) -> None:
    assert on_call_at(rotation, datetime(2026, 3, 9, 8, 0, tzinfo=UTC)) == OnCall(
        BEN, datetime(2026, 3, 16, 8, 0, tzinfo=UTC)
    )


def test_the_rotation_wraps_around(rotation: Rotation) -> None:
    assert on_call_at(rotation, datetime(2026, 3, 16, 8, 0, tzinfo=UTC)) == OnCall(
        CARA, datetime(2026, 3, 23, 8, 0, tzinfo=UTC)
    )
    assert on_call_at(rotation, datetime(2026, 3, 23, 8, 0, tzinfo=UTC)) == OnCall(
        ANNA, datetime(2026, 3, 30, 7, 0, tzinfo=UTC)
    )


def test_a_shift_across_the_spring_dst_change_ends_at_local_wall_clock_time(rotation: Rotation) -> None:
    just_before = datetime(2026, 3, 30, 6, 59, 59, 999999, tzinfo=UTC)
    assert on_call_at(rotation, just_before) == OnCall(ANNA, datetime(2026, 3, 30, 7, 0, tzinfo=UTC))
    assert on_call_at(rotation, just_before + timedelta(microseconds=1)) == OnCall(
        BEN, datetime(2026, 4, 6, 7, 0, tzinfo=UTC)
    )


def test_a_shift_across_the_autumn_dst_change_is_an_hour_longer() -> None:
    # Mondays: 2026-10-19 09:00 CEST (07:00 UTC) and 2026-10-26 09:00 CET (08:00 UTC).
    rotation = make_rotation([ANNA, BEN], datetime(2026, 10, 14, 12, 0, tzinfo=UTC))
    shift = shift_at(rotation, datetime(2026, 10, 19, 7, 0, tzinfo=UTC))
    assert shift == OnCall(BEN, datetime(2026, 10, 26, 8, 0, tzinfo=UTC))
    assert shift.until - datetime(2026, 10, 19, 7, 0, tzinfo=UTC) == timedelta(days=7, hours=1)


def test_a_handoff_time_inside_the_spring_gap_lands_after_the_gap() -> None:
    # Sunday 2026-03-29 02:30 does not exist in Prague; it resolves to 03:30 CEST (01:30 UTC).
    rotation = make_rotation([ANNA, BEN], datetime(2026, 3, 22, 12, 0, tzinfo=UTC), Weekday.SUN, time(2, 30))
    assert on_call_at(rotation, datetime(2026, 3, 29, 1, 29, tzinfo=UTC)) == OnCall(
        ANNA, datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    )
    assert on_call_at(rotation, datetime(2026, 3, 29, 1, 30, tzinfo=UTC)) == OnCall(
        BEN, datetime(2026, 4, 5, 0, 30, tzinfo=UTC)
    )


def test_a_handoff_time_in_the_autumn_overlap_takes_the_first_occurrence() -> None:
    # Sunday 2026-10-25 02:30 happens twice in Prague; the first is 02:30 CEST (00:30 UTC).
    rotation = make_rotation([ANNA, BEN], datetime(2026, 10, 18, 12, 0, tzinfo=UTC), Weekday.SUN, time(2, 30))
    assert shift_at(rotation, datetime(2026, 10, 25, 0, 29, tzinfo=UTC)) == OnCall(
        ANNA, datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    )
    assert shift_at(rotation, datetime(2026, 10, 25, 0, 30, tzinfo=UTC)).user_id == BEN
