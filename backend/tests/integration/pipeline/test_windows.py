import socket
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis

from pagercutie.core.redis import RESOLVED_MARKER_TTL_S, create_redis, dedup_window_key, resolved_marker_key
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.dedup.windows import BATCHES_KEY, DIRTY_KEY, RedisWindowStore, batch_key, counter_key

pytestmark = pytest.mark.anyio

KEY = "dedup:rule:fingerprint"
TOKEN = "pending:event-1"
NOW = datetime(2026, 11, 21, 3, 0, 0, 123456, tzinfo=UTC)


def request(key: str = KEY, token: str = TOKEN, window_s: int = 300, seen_at: datetime = NOW) -> dedup.ClaimRequest:
    return dedup.ClaimRequest(key=key, window_s=window_s, token=token, seen_at=seen_at)


async def claim(windows: dedup.WindowStore, req: dedup.ClaimRequest) -> dedup.Claim:
    [result] = await windows.claim([req])
    return result


async def confirm(
    windows: dedup.WindowStore, alert_id: uuid.UUID, key: str = KEY, ttl: timedelta | None = None
) -> None:
    await windows.confirm([dedup.Confirmation(key=key, token=TOKEN, alert_id=alert_id, ttl=ttl)])


async def count(windows: dedup.WindowStore, redis: Redis, alert_id: uuid.UUID, seen_at: datetime = NOW) -> None:
    """Count one occurrence of the alert the way ingest does: a claim on a window that holds it."""
    key = f"dedup:held:{alert_id}"
    await redis.set(key, str(alert_id))
    assert await claim(windows, request(key=key, seen_at=seen_at)) == dedup.Held(key=key, alert_id=alert_id)


@pytest.fixture
def windows(redis: Redis) -> dedup.WindowStore:
    return RedisWindowStore(redis)


@pytest.fixture
async def unreachable_redis() -> AsyncIterator[Redis]:
    """A client for a closed local port, so every command fails to connect."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    client = create_redis(f"redis://127.0.0.1:{port}/0")
    yield client
    await client.aclose()


@pytest.fixture
def unreachable(unreachable_redis: Redis) -> dedup.WindowStore:
    return RedisWindowStore(unreachable_redis)


@pytest.fixture
async def out_of_memory(redis: Redis) -> AsyncIterator[dedup.WindowStore]:
    """The test Redis refusing every write with `OOM command not allowed`, a `ResponseError`."""
    await redis.config_set("maxmemory-policy", "noeviction")
    await redis.config_set("maxmemory", 1)
    yield RedisWindowStore(redis)
    await redis.config_set("maxmemory", 0)


async def test_the_first_claim_wins_and_holds_the_events_token_for_the_window(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    assert await claim(windows, request()) == dedup.Won(key=KEY)
    assert await redis.get(KEY) == TOKEN
    assert 0 < await redis.ttl(KEY) <= 300


async def test_a_claim_on_an_unconfirmed_window_is_pending(windows: dedup.WindowStore) -> None:
    await claim(windows, request())

    assert await claim(windows, request(token="pending:event-2")) == dedup.Pending(key=KEY)


async def test_one_call_claims_every_window_in_order(windows: dedup.WindowStore, redis: Redis) -> None:
    alert_id = uuid.uuid7()
    await redis.set("dedup:held", str(alert_id))
    await redis.set("dedup:pending", "pending:other")

    claims = await windows.claim([request("dedup:new"), request("dedup:held"), request("dedup:pending")])

    assert claims == [
        dedup.Won(key="dedup:new"),
        dedup.Held(key="dedup:held", alert_id=alert_id),
        dedup.Pending(key="dedup:pending"),
    ]


async def test_a_held_claim_counts_the_occurrence_and_keeps_the_newest_time(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    alert_id = uuid.uuid7()

    await count(windows, redis, alert_id, NOW + timedelta(seconds=5))
    await count(windows, redis, alert_id, NOW)

    assert await redis.hgetall(counter_key(alert_id)) == {"n": "2", "seen": "1795230005123456"}
    assert await redis.smembers(DIRTY_KEY) == {str(alert_id)}


async def test_a_confirmed_window_is_held_by_its_alert_with_the_claims_ttl(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    alert_id = uuid.uuid7()
    await claim(windows, request())
    await redis.expire(KEY, 100)

    await confirm(windows, alert_id)

    assert await claim(windows, request(token="pending:event-2")) == dedup.Held(key=KEY, alert_id=alert_id)
    assert 0 < await redis.ttl(KEY) <= 100


async def test_a_confirmation_with_a_ttl_replaces_the_claims(windows: dedup.WindowStore, redis: Redis) -> None:
    await claim(windows, request())

    await confirm(windows, uuid.uuid7(), ttl=timedelta(seconds=42))

    assert 40 <= await redis.ttl(KEY) <= 42


async def test_confirm_does_not_recreate_an_expired_window(windows: dedup.WindowStore, redis: Redis) -> None:
    await confirm(windows, uuid.uuid7())

    assert await redis.exists(KEY) == 0


async def test_confirm_and_release_leave_a_window_another_event_claimed(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    await redis.set(KEY, "pending:event-2")

    await confirm(windows, uuid.uuid7())
    await windows.release([dedup.Ownership(key=KEY, token=TOKEN)])

    assert await redis.get(KEY) == "pending:event-2"


async def test_a_released_window_is_won_again(windows: dedup.WindowStore) -> None:
    await claim(windows, request())

    await windows.release([dedup.Ownership(key=KEY, token=TOKEN)])

    assert await claim(windows, request()) == dedup.Won(key=KEY)


async def test_a_window_holding_neither_a_token_nor_an_alert_id_goes_to_postgres(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    await redis.set(KEY, "garbage")

    assert await claim(windows, request()) == dedup.Pending(key=KEY)


async def test_marking_an_alert_resolved_deletes_its_window_so_the_next_match_wins(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    rule_id, alert_id = uuid.uuid7(), uuid.uuid7()
    key = dedup_window_key(rule_id, "a" * 64)
    await claim(windows, request(key=key))
    await confirm(windows, alert_id, key=key)

    await windows.mark_resolved(alert_id, rule_id, "a" * 64)

    assert await claim(windows, request(key=key, token="pending:event-2")) == dedup.Won(key=key)
    assert 0 < await redis.ttl(resolved_marker_key(alert_id)) <= RESOLVED_MARKER_TTL_S


async def test_marking_an_alert_resolved_leaves_a_window_of_another_alert(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    rule_id, newer = uuid.uuid7(), uuid.uuid7()
    key = dedup_window_key(rule_id, "a" * 64)
    await redis.set(key, str(newer))

    await windows.mark_resolved(uuid.uuid7(), rule_id, "a" * 64)

    assert await redis.get(key) == str(newer)


async def test_a_window_still_holding_a_resolved_alert_is_won_and_counts_nothing(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    # The gap: a window that held the alert when the resolve marked it, or got it back from a late confirm.
    alert_id = uuid.uuid7()
    await windows.mark_resolved(alert_id, uuid.uuid7(), "a" * 64)
    await redis.set(KEY, str(alert_id))

    assert await claim(windows, request()) == dedup.Won(key=KEY)
    assert await redis.get(KEY) == TOKEN
    assert await redis.exists(counter_key(alert_id), DIRTY_KEY) == 0


async def test_a_late_confirm_of_a_resolved_alert_deletes_the_window(windows: dedup.WindowStore, redis: Redis) -> None:
    alert_id = uuid.uuid7()
    await claim(windows, request())
    await windows.mark_resolved(alert_id, uuid.uuid7(), "a" * 64)

    await confirm(windows, alert_id)

    assert await redis.exists(KEY) == 0


async def test_drain_moves_marked_counters_into_the_batch(windows: dedup.WindowStore, redis: Redis) -> None:
    alert_id = uuid.uuid7()
    await count(windows, redis, alert_id, NOW)
    await count(windows, redis, alert_id, NOW + timedelta(seconds=5))

    assert await windows.drain("b1", 10) == [
        dedup.Counter(alert_id=alert_id, occurrences=2, last_seen_at=NOW + timedelta(seconds=5))
    ]
    assert await redis.exists(counter_key(alert_id), DIRTY_KEY) == 0
    assert await redis.hgetall(batch_key("b1")) == {str(alert_id): "2:1795230005123456"}
    assert await redis.zrange(BATCHES_KEY, 0, -1) == [batch_key("b1")]
    assert await windows.drain("b2", 10) == []


async def test_drain_takes_at_most_the_limit(windows: dedup.WindowStore, redis: Redis) -> None:
    for _ in range(3):
        await count(windows, redis, uuid.uuid7())

    assert len(await windows.drain("b1", 2)) == 2
    assert len(await windows.drain("b2", 2)) == 1


async def test_ack_forgets_the_batch(windows: dedup.WindowStore, redis: Redis) -> None:
    await count(windows, redis, uuid.uuid7())
    await windows.drain("b1", 10)

    await windows.ack("b1")

    assert await redis.exists(batch_key("b1"), BATCHES_KEY) == 0
    assert await windows.recover(0) == 0


async def test_restore_adds_a_batch_to_newer_counts(windows: dedup.WindowStore, redis: Redis) -> None:
    alert_id = uuid.uuid7()
    await count(windows, redis, alert_id, NOW)
    await windows.drain("b1", 10)
    await count(windows, redis, alert_id, NOW - timedelta(seconds=1))

    await windows.restore("b1")

    assert await redis.exists(batch_key("b1"), BATCHES_KEY) == 0
    assert await windows.drain("b2", 10) == [dedup.Counter(alert_id=alert_id, occurrences=2, last_seen_at=NOW)]


async def test_recover_restores_only_batches_old_enough(windows: dedup.WindowStore, redis: Redis) -> None:
    alert_id = uuid.uuid7()
    await count(windows, redis, alert_id)
    await windows.drain("abandoned", 10)

    assert await windows.recover(3600) == 0
    assert await windows.recover(0) == 1

    assert await redis.exists(batch_key("abandoned"), BATCHES_KEY) == 0
    assert await windows.drain("next", 10) == [dedup.Counter(alert_id=alert_id, occurrences=1, last_seen_at=NOW)]


async def test_an_unreachable_redis_sends_claims_to_postgres_and_never_raises(unreachable: dedup.WindowStore) -> None:
    assert await unreachable.claim([request()]) == [dedup.Unavailable(key=KEY)]
    await unreachable.confirm([dedup.Confirmation(key=KEY, token=TOKEN, alert_id=uuid.uuid7(), ttl=None)])
    await unreachable.release([dedup.Ownership(key=KEY, token=TOKEN)])
    await unreachable.mark_resolved(uuid.uuid7(), uuid.uuid7(), "a" * 64)
    assert await unreachable.drain("b1", 10) == []
    await unreachable.ack("b1")
    await unreachable.restore("b1")
    assert await unreachable.recover(0) == 0


async def test_a_redis_answering_with_an_error_degrades_like_an_unreachable_one(
    out_of_memory: dedup.WindowStore,
) -> None:
    assert await out_of_memory.claim([request()]) == [dedup.Unavailable(key=KEY)]
    await out_of_memory.confirm([dedup.Confirmation(key=KEY, token=TOKEN, alert_id=uuid.uuid7(), ttl=None)])
    await out_of_memory.release([dedup.Ownership(key=KEY, token=TOKEN)])
    await out_of_memory.mark_resolved(uuid.uuid7(), uuid.uuid7(), "a" * 64)
    assert await out_of_memory.drain("b1", 10) == []
    await out_of_memory.restore("b1")
