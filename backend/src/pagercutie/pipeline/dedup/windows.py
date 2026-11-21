"""`WindowStore` on Redis: dedup window claims and per-alert occurrence counters (SPEC §5.2)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis

from pagercutie.core.redis import UNREACHABLE
from pagercutie.pipeline.dedup.stage import Claim, Counter, Held, Pending, Unavailable, Won

log = structlog.get_logger("dedup")

# Value of a claimed window until `confirm` replaces it with the alert ID.
PENDING = "pending"
# Alert IDs whose counters changed since the last flush.
DIRTY_KEY = "count:dirty"

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# KEYS: counter hash, dirty set. ARGV: occurrences, seen_at in epoch microseconds, alert ID.
# One script, so the count, the newest time and the dirty mark change together.
_ADD = """
redis.call('HINCRBY', KEYS[1], 'n', ARGV[1])
local seen = redis.call('HGET', KEYS[1], 'seen')
if not seen or tonumber(seen) < tonumber(ARGV[2]) then
  redis.call('HSET', KEYS[1], 'seen', ARGV[2])
end
redis.call('SADD', KEYS[2], ARGV[3])
"""

# KEYS: dirty set. ARGV: limit, counter key prefix. Returns [alert_id, n, seen, ...].
# Atomic, so an increment lands either in this batch or in a fresh counter for the next one.
_DRAIN = """
local out = {}
for _, id in ipairs(redis.call('SPOP', KEYS[1], ARGV[1])) do
  local key = ARGV[2] .. id
  local counter = redis.call('HMGET', key, 'n', 'seen')
  redis.call('DEL', key)
  if counter[1] and counter[2] then
    table.insert(out, id)
    table.insert(out, counter[1])
    table.insert(out, counter[2])
  end
end
return out
"""

_COUNTER_PREFIX = "count:"


def counter_key(alert_id: uuid.UUID) -> str:
    """Redis hash of the alert's unflushed occurrences: `n` (count) and `seen` (newest, epoch microseconds)."""
    return f"{_COUNTER_PREFIX}{alert_id}"


class RedisWindowStore:
    """Needs a client created with `decode_responses=True` (`core.redis.create_redis`)."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._add = redis.register_script(_ADD)
        self._drain = redis.register_script(_DRAIN)

    async def claim(self, key: str, window_s: int) -> Claim:
        try:
            previous = await self._redis.set(key, PENDING, ex=window_s, nx=True, get=True)
        except UNREACHABLE:
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
        except UNREACHABLE:
            log.warning("dedup.redis_unavailable", operation="confirm", key=key)

    async def release(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except UNREACHABLE:
            log.warning("dedup.redis_unavailable", operation="release", key=key)

    async def increment(self, alert_id: uuid.UUID, seen_at: datetime) -> None:
        try:
            await self._add_counter(Counter(alert_id=alert_id, occurrences=1, last_seen_at=seen_at))
        except UNREACHABLE:
            log.warning("dedup.redis_unavailable", operation="increment", alert_id=str(alert_id))

    async def drain(self, limit: int) -> list[Counter]:
        try:
            reply = await self._drain(keys=[DIRTY_KEY], args=[limit, _COUNTER_PREFIX])
        except UNREACHABLE:
            log.warning("dedup.redis_unavailable", operation="drain")
            return []
        if not isinstance(reply, list) or len(reply) % 3 or not all(isinstance(item, str) for item in reply):
            raise TypeError(f"drain script returned {reply!r}")
        return [
            Counter(
                alert_id=uuid.UUID(alert_id),
                occurrences=int(n),
                last_seen_at=_EPOCH + timedelta(microseconds=int(seen)),
            )
            for alert_id, n, seen in zip(reply[0::3], reply[1::3], reply[2::3], strict=True)
        ]

    async def restore(self, counters: Sequence[Counter]) -> None:
        try:
            for counter in counters:
                await self._add_counter(counter)
        except UNREACHABLE:
            log.warning("dedup.counts_lost", message="Redis unreachable; drained counts are lost", alerts=len(counters))

    async def _add_counter(self, counter: Counter) -> None:
        seen_us = (counter.last_seen_at - _EPOCH) // timedelta(microseconds=1)
        alert_id = str(counter.alert_id)
        await self._add(keys=[counter_key(counter.alert_id), DIRTY_KEY], args=[counter.occurrences, seen_us, alert_id])
