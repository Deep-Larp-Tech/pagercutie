import pytest

from pagercutie.core.errors import Overloaded
from pagercutie.pipeline.admission import InFlight, SourceRateLimit


def test_a_full_replica_refuses_at_once_and_frees_the_slot_when_a_request_ends() -> None:
    in_flight = InFlight(limit=2)

    with in_flight.slot(), in_flight.slot():
        with pytest.raises(Overloaded) as refused, in_flight.slot():
            pass
        assert refused.value.retry_after_s == 1
        assert in_flight.count == 2

    assert in_flight.count == 0
    with in_flight.slot():
        assert in_flight.count == 1


def test_a_slot_is_freed_when_the_request_fails() -> None:
    in_flight = InFlight(limit=1)

    with pytest.raises(RuntimeError), in_flight.slot():
        raise RuntimeError("boom")

    assert in_flight.count == 0


def test_buckets_are_per_source_and_credential_so_a_wrong_token_cannot_drain_the_right_one() -> None:
    right = SourceRateLimit.bucket("payments", "Bearer right")

    assert right == SourceRateLimit.bucket("payments", "Bearer right")
    assert right != SourceRateLimit.bucket("payments", "Bearer wrong")
    assert right != SourceRateLimit.bucket("orders", "Bearer right")
    assert right.startswith("payments:")
    assert "right" not in right
