"""Per-recipient token buckets in Redis, shared by the dispatchers of every replica (SPEC §5.2, §9)."""

import uuid
from typing import assert_never

import redis.asyncio as redis
import structlog

from pagercutie.core.token_bucket import Empty, Taken, TokenBuckets

log = structlog.get_logger("dispatch")


class RedisThrottle:
    """A token bucket per user under `throttle:{user_id}`: `capacity` messages at once, then one more every
    `refill_seconds` (ADR-0083). A failed send gives its token back (ADR-0109)."""

    def __init__(self, client: redis.Redis, capacity: int, refill_seconds: float) -> None:
        self._buckets = TokenBuckets(client, "throttle", capacity, refill_seconds)

    async def allow(self, user_id: uuid.UUID) -> bool:
        """Take one token for `user_id`. True when Redis cannot be reached: throttling fails open (SPEC §5.2)."""
        try:
            taken = await self._buckets.take(str(user_id))
        except redis.RedisError:
            log.warning(
                "dispatch.throttle_unavailable", message="Redis unreachable, not throttling", user_id=str(user_id)
            )
            return True
        match taken:
            case Taken():
                return True
            case Empty():
                return False
            case _:
                assert_never(taken)

    async def refund(self, user_id: uuid.UUID) -> None:
        """Give back the token of a send that failed; the bucket never exceeds its capacity."""
        try:
            await self._buckets.refund(str(user_id))
        except redis.RedisError:
            log.warning(
                "dispatch.throttle_unavailable", message="Redis unreachable, token not refunded", user_id=str(user_id)
            )
