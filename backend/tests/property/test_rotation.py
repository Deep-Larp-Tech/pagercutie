import uuid
from datetime import UTC, datetime, time, timedelta

from hypothesis import given
from hypothesis import strategies as st

from pagercutie.core.enums import Weekday
from pagercutie.teams.models import Rotation, RotationMember
from pagercutie.teams.rotation import OnCall, on_call_at

ZONES = ["UTC", "Europe/Prague", "America/New_York", "Asia/Kolkata", "Australia/Lord_Howe", "Pacific/Auckland"]
MICROSECOND = timedelta(microseconds=1)


def build(user_ids: list[uuid.UUID], started_at: datetime, day: Weekday, at: time, timezone: str) -> Rotation:
    rotation = Rotation(
        team_id=uuid.UUID(int=0),
        handoff_day=day,
        handoff_time=at,
        timezone=timezone,
        members=[RotationMember(user_id=user_id, position=position) for position, user_id in enumerate(user_ids)],
    )
    rotation.started_at = started_at
    return rotation


def shift_at(rotation: Rotation, now: datetime) -> OnCall:
    result = on_call_at(rotation, now)
    assert result is not None
    return result


instants = st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31), timezones=st.just(UTC))
rotations = st.builds(
    build,
    st.lists(st.uuids(), min_size=1, max_size=6, unique=True),
    instants,
    st.sampled_from(Weekday),
    st.times(),
    st.sampled_from(ZONES),
)
offsets = st.timedeltas(min_value=timedelta(0), max_value=timedelta(days=3 * 365))


@given(rotations, offsets)
def test_the_on_call_user_is_always_a_member(rotation: Rotation, offset: timedelta) -> None:
    shift = shift_at(rotation, rotation.started_at + offset)
    assert shift.user_id in {member.user_id for member in rotation.members}


@given(rotations, offsets)
def test_the_shift_ends_after_now_and_within_a_week_and_an_hour(rotation: Rotation, offset: timedelta) -> None:
    now = rotation.started_at + offset
    shift = shift_at(rotation, now)
    assert now < shift.until <= now + timedelta(days=7, hours=1)
    assert shift.until.utcoffset() == timedelta(0)


@given(rotations, offsets)
def test_the_same_user_is_on_call_until_the_last_microsecond_of_the_shift(
    rotation: Rotation, offset: timedelta
) -> None:
    now = rotation.started_at + offset
    shift = shift_at(rotation, now)
    assert shift_at(rotation, shift.until - MICROSECOND) == shift


@given(rotations, offsets)
def test_the_next_member_takes_over_at_the_end_of_the_shift(rotation: Rotation, offset: timedelta) -> None:
    shift = shift_at(rotation, rotation.started_at + offset)
    following = shift_at(rotation, shift.until)
    ids = [member.user_id for member in rotation.members]
    assert following.user_id == ids[(ids.index(shift.user_id) + 1) % len(ids)]
    assert following.until > shift.until
    if len(ids) > 1:
        assert following.user_id != shift.user_id


@given(rotations)
def test_one_full_cycle_visits_every_member_in_order_and_returns_to_the_first(rotation: Rotation) -> None:
    ids = [member.user_id for member in rotation.members]
    shift = shift_at(rotation, rotation.started_at)
    visited: list[uuid.UUID] = []
    for _ in ids:
        visited.append(shift.user_id)
        shift = shift_at(rotation, shift.until)
    assert visited == ids
    assert shift.user_id == ids[0]
