"""The Redis client every replica shares state through: dedup windows, occurrence counters, throttles (SPEC §5.2)."""

import uuid

import structlog
from fastapi import Request
from redis import exceptions as redis_errors
from redis.asyncio import Redis

log = structlog.get_logger("redis")

# Short, so an unreachable Redis sends a match down the Postgres path (SPEC §5.2) instead of stalling ingest.
TIMEOUT_S = 0.5

# Errors that mean Redis cannot be reached; callers degrade instead of failing (SPEC §5.2).
UNREACHABLE = (redis_errors.ConnectionError, redis_errors.TimeoutError)


def create_redis(url: str) -> Redis:
    """Client that decodes replies to `str`; connects lazily, so creating it never fails."""
    return Redis.from_url(url, decode_responses=True, socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S)


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def dedup_window_key(rule_id: uuid.UUID, fingerprint: str) -> str:
    """Redis key of a dedup window, `dedup:{rule_id}:{fingerprint}`."""
    return f"dedup:{rule_id}:{fingerprint}"


async def delete_dedup_window(redis: Redis, rule_id: uuid.UUID, fingerprint: str) -> None:
    """Delete a resolved alert's dedup window, so the next match opens a new alert instead of counting on it.

    Call after the resolve commits, for manual and automatic (RUN-5) resolves. With Redis unreachable the window
    expires on its own within `window_s`.
    """
    key = dedup_window_key(rule_id, fingerprint)
    try:
        await redis.delete(key)
    except UNREACHABLE:
        log.warning("redis.unavailable", operation="delete_dedup_window", key=key)
