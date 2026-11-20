from hypothesis import given
from hypothesis import strategies as st

from larper.persons.elo import K_FACTOR, elo_delta

elos = st.integers(min_value=0, max_value=10_000)
levels = st.integers(min_value=1, max_value=10)


@given(elo=elos, difficulty=levels, believability=levels)
def test_delta_is_bounded_and_elo_never_negative(elo: int, difficulty: int, believability: int) -> None:
    delta = elo_delta(elo, difficulty, believability)

    assert -K_FACTOR <= delta <= K_FACTOR
    assert elo + delta >= 0


@given(elo=elos, difficulty=levels, believability=st.integers(min_value=1, max_value=9))
def test_more_believable_never_earns_less(elo: int, difficulty: int, believability: int) -> None:
    assert elo_delta(elo, difficulty, believability + 1) >= elo_delta(elo, difficulty, believability)


@given(elo=elos, difficulty=st.integers(min_value=1, max_value=9), believability=levels)
def test_harder_skill_never_earns_less(elo: int, difficulty: int, believability: int) -> None:
    assert elo_delta(elo, difficulty + 1, believability) >= elo_delta(elo, difficulty, believability)
