"""Per-recipient token buckets in Redis, shared by the dispatchers of every replica (SPEC §5.2, §9)."""

import uuid

import redis.asyncio as redis
import structlog

log = structlog.get_logger("dispatch")

# Refills from Redis's own clock, so replicas with skewed clocks share one bucket. The key expires once the bucket
# would be full again (plus a margin), which is the same as a missing key: idle users cost no memory.
TOKEN_BUCKET = """
local capacity = tonumber(ARGV[1])
local refill_ms = tonumber(ARGV[2])
local time = redis.call('TIME')
local now_ms = time[1] * 1000 + math.floor(time[2] / 1000)
local state = redis.call('HMGET', KEYS[1], 'tokens', 'at')
local tokens = tonumber(state[1])
if tokens == nil then
    tokens = capacity
else
    tokens = math.min(capacity, tokens + math.max(0, now_ms - tonumber(state[2])) / refill_ms)
end
local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'at', now_ms)
redis.call('PEXPIRE', KEYS[1], math.ceil((capacity - tokens) * refill_ms) + 1000)
return allowed
"""


class RedisThrottle:
    """A token bucket per user: `capacity` messages at once, then one more every `refill_seconds`."""

    def __init__(self, client: redis.Redis, capacity: int, refill_seconds: float) -> None:
        self._script = client.register_script(TOKEN_BUCKET)
        self._capacity = capacity
        self._refill_ms = refill_seconds * 1000

    async def allow(self, user_id: uuid.UUID) -> bool:
        """Take one token for `user_id`. True when Redis cannot be reached: throttling fails open (SPEC §5.2)."""
        try:
            taken = await self._script(keys=[f"throttle:{user_id}"], args=[self._capacity, self._refill_ms])
        except redis.RedisError:
            log.warning(
                "dispatch.throttle_unavailable", message="Redis unreachable, not throttling", user_id=str(user_id)
            )
            return True
        return taken == 1
