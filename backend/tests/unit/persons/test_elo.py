import pytest

from pagercutie.persons.elo import elo_delta


@pytest.mark.parametrize(
    ("elo", "difficulty", "believability", "expected"),
    [
        (1000, 2, 10, 16),  # even match (skill rating 1000), perfect performance: +K/2
        (1000, 2, 1, -16),  # even match, worst performance: -K/2
        (1000, 10, 10, 32),  # nailing a much harder skill pays the full K
        (1000, 10, 1, 0),  # failing a much harder skill was expected: costs nothing
        (1800, 1, 10, 0),  # an easy skill teaches a strong person nothing
        (1800, 1, 1, -32),  # ...but botching it costs the full K
        (0, 1, 1, 0),  # zero Elo stays non-negative
    ],
)
def test_elo_delta(elo: int, difficulty: int, believability: int, expected: int) -> None:
    assert elo_delta(elo, difficulty, believability) == expected
