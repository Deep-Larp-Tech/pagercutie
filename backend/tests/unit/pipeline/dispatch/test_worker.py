import pytest

from pagercutie.core.settings import Settings
from pagercutie.pipeline.dispatch.worker import MAX_CONCURRENT_SENDS, claim_limit


@pytest.mark.parametrize(
    ("batch_size", "expected"),
    [(1, 1), (MAX_CONCURRENT_SENDS, MAX_CONCURRENT_SENDS), (MAX_CONCURRENT_SENDS + 1, MAX_CONCURRENT_SENDS), (500, 16)],
)
def test_the_loop_never_runs_more_sends_than_max_concurrent_sends(batch_size: int, expected: int) -> None:
    assert claim_limit(Settings(delivery_batch_size=batch_size)) == expected
