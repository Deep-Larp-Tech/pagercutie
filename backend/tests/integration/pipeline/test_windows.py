import socket
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis

from pagercutie.core.redis import create_redis, dedup_window_key, delete_dedup_window
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.dedup.windows import DIRTY_KEY, PENDING, RedisWindowStore, counter_key

pytestmark = pytest.mark.anyio

KEY = "dedup:rule:fingerprint"
NOW = datetime(2026, 11, 21, 3, 0, 0, 123456, tzinfo=UTC)


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = create_redis(redis_url)
    await client.flushdb()
    yield client
    await client.aclose()


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


async def test_the_first_claim_wins_and_holds_pending_for_the_window(windows: dedup.WindowStore, redis: Redis) -> None:
    assert await windows.claim(KEY, 300) == dedup.Won(key=KEY)
    assert await redis.get(KEY) == PENDING
    assert 0 < await redis.ttl(KEY) <= 300


async def test_a_claim_on_an_unconfirmed_window_is_pending(windows: dedup.WindowStore) -> None:
    await windows.claim(KEY, 300)

    assert await windows.claim(KEY, 300) == dedup.Pending(key=KEY)


async def test_a_claim_on_a_confirmed_window_is_held_by_its_alert(windows: dedup.WindowStore, redis: Redis) -> None:
    alert_id = uuid.uuid7()
    await windows.claim(KEY, 300)
    await redis.expire(KEY, 100)

    await windows.confirm(KEY, alert_id)

    assert await windows.claim(KEY, 300) == dedup.Held(key=KEY, alert_id=alert_id)
    assert 0 < await redis.ttl(KEY) <= 100


async def test_confirm_does_not_recreate_an_expired_window(windows: dedup.WindowStore, redis: Redis) -> None:
    await windows.confirm(KEY, uuid.uuid7())

    assert await redis.exists(KEY) == 0


async def test_a_released_window_is_won_again(windows: dedup.WindowStore) -> None:
    await windows.claim(KEY, 300)

    await windows.release(KEY)

    assert await windows.claim(KEY, 300) == dedup.Won(key=KEY)


async def test_a_window_holding_neither_pending_nor_an_alert_id_goes_to_postgres(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    await redis.set(KEY, "garbage")

    assert await windows.claim(KEY, 300) == dedup.Pending(key=KEY)


async def test_increment_counts_keeps_the_newest_time_and_marks_the_alert_dirty(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    alert_id = uuid.uuid7()
    newest = NOW + timedelta(seconds=5)

    await windows.increment(alert_id, newest)
    await windows.increment(alert_id, NOW)

    counter = await redis.hgetall(counter_key(alert_id))
    assert counter == {"n": "2", "seen": "1795230005123456"}
    assert await redis.smembers(DIRTY_KEY) == {str(alert_id)}


async def test_an_unreachable_redis_sends_claims_to_postgres_and_never_raises(unreachable: dedup.WindowStore) -> None:
    assert await unreachable.claim(KEY, 300) == dedup.Unavailable(key=KEY)
    await unreachable.confirm(KEY, uuid.uuid7())
    await unreachable.release(KEY)
    await unreachable.increment(uuid.uuid7(), NOW)


async def test_deleting_a_resolved_alerts_window_lets_the_next_match_win(
    windows: dedup.WindowStore, redis: Redis
) -> None:
    rule_id = uuid.uuid7()
    key = dedup_window_key(rule_id, "a" * 64)
    await windows.claim(key, 300)
    await windows.confirm(key, uuid.uuid7())

    await delete_dedup_window(redis, rule_id, "a" * 64)

    assert await windows.claim(key, 300) == dedup.Won(key=key)


async def test_deleting_a_window_with_redis_unreachable_does_not_raise(unreachable_redis: Redis) -> None:
    await delete_dedup_window(unreachable_redis, uuid.uuid7(), "a" * 64)
