import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import redis.asyncio as redis
from testcontainers.community.redis import RedisContainer

from pagercutie.pipeline.dispatch.throttle import RedisThrottle

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:8-alpine") as container:
        yield container


@pytest.fixture
async def client(redis_container: RedisContainer) -> AsyncIterator[redis.Redis]:
    client = redis.Redis(host=redis_container.get_container_host_ip(), port=int(redis_container.get_exposed_port(6379)))
    yield client
    await client.flushdb()
    await client.aclose()


async def test_a_bucket_allows_its_capacity_then_refills_one_token_at_a_time(client: redis.Redis) -> None:
    throttle = RedisThrottle(client, capacity=3, refill_seconds=0.5)
    user = uuid.uuid4()

    assert [await throttle.allow(user) for _ in range(4)] == [True, True, True, False]

    await asyncio.sleep(0.6)
    assert [await throttle.allow(user) for _ in range(2)] == [True, False]


async def test_buckets_are_per_user(client: redis.Redis) -> None:
    throttle = RedisThrottle(client, capacity=1, refill_seconds=60)

    assert await throttle.allow(uuid.uuid4())
    assert await throttle.allow(uuid.uuid4())


async def test_a_bucket_never_holds_more_than_its_capacity(client: redis.Redis) -> None:
    throttle = RedisThrottle(client, capacity=2, refill_seconds=0.05)
    user = uuid.uuid4()

    await asyncio.sleep(0.3)

    assert [await throttle.allow(user) for _ in range(3)] == [True, True, False]


async def test_an_idle_bucket_expires(client: redis.Redis) -> None:
    throttle = RedisThrottle(client, capacity=2, refill_seconds=0.1)
    user = uuid.uuid4()
    await throttle.allow(user)

    ttl = await client.pttl(f"throttle:{user}")

    # Time to refill the missing token, plus the margin the script adds.
    assert 0 < ttl <= 1100


async def test_throttling_fails_open_when_redis_is_unreachable() -> None:
    unreachable = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.5)
    throttle = RedisThrottle(unreachable, capacity=1, refill_seconds=60)

    assert [await throttle.allow(uuid.uuid4()) for _ in range(3)] == [True, True, True]

    await unreachable.aclose()
