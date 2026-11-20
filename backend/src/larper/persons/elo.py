DEFAULT_ELO = 1000
K_FACTOR = 32


def skill_rating(difficulty: int) -> int:
    return 800 + difficulty * 100


def expected_score(elo: int, difficulty: int) -> float:
    return 1 / (1 + 10 ** ((skill_rating(difficulty) - elo) / 400))


def performance(believability: int) -> float:
    return (believability - 1) / 9


def elo_delta(elo: int, difficulty: int, believability: int) -> int:
    """Rating change for one event; never drops the rating below zero (guard, see property tests)."""
    delta = round(K_FACTOR * (performance(believability) - expected_score(elo, difficulty)))
    return max(delta, -elo)
