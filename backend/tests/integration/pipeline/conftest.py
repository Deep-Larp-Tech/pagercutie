from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from pagercutie.core.redis import create_redis


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    """A client for the test Redis, emptied before each test."""
    client = create_redis(redis_url)
    await client.flushdb()
    yield client
    await client.aclose()
