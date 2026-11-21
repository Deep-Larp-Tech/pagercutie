"""Token buckets in Redis shared by every replica: recipient throttles (SPEC §9) and ingest source limits (ADR-0111)."""

import math
from dataclasses import dataclass

import redis.asyncio as redis

# Refills from Redis's own clock, so replicas with skewed clocks share one bucket. A missing key is a full bucket.
_REFILL = """
local capacity = tonumber(ARGV[1])
local refill_ms = tonumber(ARGV[2])
local time = redis.call('TIME')
local now_ms = time[1] * 1000 + math.floor(time[2] / 1000)
local state = redis.call('HMGET', KEYS[1], 'tokens', 'at')
local tokens = tonumber(state[1])
local missing = tokens == nil
if missing then
    tokens = capacity
else
    tokens = math.min(capacity, tokens + math.max(0, now_ms - tonumber(state[2])) / refill_ms)
end
"""

# The key expires once the bucket would be full again (plus a margin), which is the same as a missing key: idle
# buckets cost no memory.
_STORE = """
redis.call('HSET', KEYS[1], 'tokens', tokens, 'at', now_ms)
redis.call('PEXPIRE', KEYS[1], math.ceil((capacity - tokens) * refill_ms) + 1000)
"""

# Returns {1, 0} when a token was taken, else {0, milliseconds until the next token}.
TAKE = (
    _REFILL
    + """
local allowed = 0
local wait_ms = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
else
    wait_ms = math.ceil((1 - tokens) * refill_ms)
end
"""
    + _STORE
    + """
return {allowed, wait_ms}
"""
)

# Gives back one token, never above `capacity`. Returns 1 when a token was added, 0 when the bucket was full.
REFUND = (
    _REFILL
    + """
if missing or tokens >= capacity then
    return 0
end
tokens = math.min(capacity, tokens + 1)
"""
    + _STORE
    + """
return 1
"""
)


@dataclass(frozen=True)
class Taken:
    """A token was taken from the bucket."""


@dataclass(frozen=True)
class Empty:
    """The bucket is empty."""

    # Seconds until the bucket holds a token again, rounded up.
    retry_after_s: int


type TakeResult = Taken | Empty


class TokenBuckets:
    """Buckets under `{prefix}:{key}`: `capacity` tokens at once, then one more every `refill_seconds`.

    Every call raises `redis.RedisError` when Redis cannot be reached; callers decide whether to fail open.
    """

    def __init__(self, client: redis.Redis, prefix: str, capacity: int, refill_seconds: float) -> None:
        self._take = client.register_script(TAKE)
        self._refund = client.register_script(REFUND)
        self._prefix = prefix
        self._args = [capacity, refill_seconds * 1000]

    def key(self, key: str) -> str:
        """The Redis key of one bucket."""
        return f"{self._prefix}:{key}"

    async def take(self, key: str) -> TakeResult:
        """Take one token from the bucket `key`."""
        match await self._take(keys=[self.key(key)], args=self._args):
            case [1, _]:
                return Taken()
            case [0, int(wait_ms)]:
                return Empty(retry_after_s=max(1, math.ceil(wait_ms / 1000)))
            case reply:
                raise redis.RedisError(f"Unexpected token bucket reply {reply!r}")

    async def refund(self, key: str) -> bool:
        """Give one token back to the bucket `key`, capped at its capacity. True when a token was added."""
        return await self._refund(keys=[self.key(key)], args=self._args) == 1
