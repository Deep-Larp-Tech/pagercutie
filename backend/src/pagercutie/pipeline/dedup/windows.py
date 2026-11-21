"""`WindowStore` on Redis: dedup window claims and per-alert occurrence counters (SPEC §5.2)."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from redis import exceptions as redis_errors
from redis.asyncio import Redis

from pagercutie.pipeline.dedup.stage import Claim, Held, Pending, Unavailable, Won

log = structlog.get_logger("dedup")

# Value of a claimed window until `confirm` replaces it with the alert ID.
PENDING = "pending"
# Alert IDs whose counters changed since the last flush.
DIRTY_KEY = "count:dirty"

_UNREACHABLE = (redis_errors.ConnectionError, redis_errors.TimeoutError)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# KEYS: counter hash, dirty set. ARGV: seen_at in epoch microseconds, alert ID.
# One script, so the count, the newest time and the dirty mark change together.
_INCREMENT = """
redis.call('HINCRBY', KEYS[1], 'n', 1)
local seen = redis.call('HGET', KEYS[1], 'seen')
if not seen or tonumber(seen) < tonumber(ARGV[1]) then
  redis.call('HSET', KEYS[1], 'seen', ARGV[1])
end
redis.call('SADD', KEYS[2], ARGV[2])
"""


def counter_key(alert_id: uuid.UUID) -> str:
    """Redis hash of the alert's unflushed occurrences: `n` (count) and `seen` (newest, epoch microseconds)."""
    return f"count:{alert_id}"


class RedisWindowStore:
    """Needs a client created with `decode_responses=True` (`core.redis.create_redis`)."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._increment = redis.register_script(_INCREMENT)

    async def claim(self, key: str, window_s: int) -> Claim:
        try:
            previous = await self._redis.set(key, PENDING, ex=window_s, nx=True, get=True)
        except _UNREACHABLE:
            log.warning("dedup.redis_unavailable", operation="claim", key=key)
            return Unavailable(key=key)
        match previous:
            case None:
                return Won(key=key)
            case str() if previous == PENDING:
                return Pending(key=key)
            case str():
                try:
                    return Held(key=key, alert_id=uuid.UUID(previous))
                except ValueError:
                    # Postgres decides whatever the key holds (SPEC §5.2).
                    log.warning("dedup.window_value_invalid", key=key, value=previous)
                    return Pending(key=key)
            case _:
                raise TypeError(f"Redis client must decode responses; SET returned {type(previous).__name__}")

    async def confirm(self, key: str, alert_id: uuid.UUID) -> None:
        try:
            await self._redis.set(key, str(alert_id), xx=True, keepttl=True)
        except _UNREACHABLE:
            log.warning("dedup.redis_unavailable", operation="confirm", key=key)

    async def release(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except _UNREACHABLE:
            log.warning("dedup.redis_unavailable", operation="release", key=key)

    async def increment(self, alert_id: uuid.UUID, seen_at: datetime) -> None:
        seen_us = (seen_at - _EPOCH) // timedelta(microseconds=1)
        try:
            await self._increment(keys=[counter_key(alert_id), DIRTY_KEY], args=[seen_us, str(alert_id)])
        except _UNREACHABLE:
            log.warning("dedup.redis_unavailable", operation="increment", alert_id=str(alert_id))
