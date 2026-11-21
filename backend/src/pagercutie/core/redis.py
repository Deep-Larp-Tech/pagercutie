"""The Redis client every replica shares state through: dedup windows, occurrence counters, throttles (SPEC §5.2)."""

from fastapi import Request
from redis.asyncio import Redis

# Short, so an unreachable Redis sends a match down the Postgres path (SPEC §5.2) instead of stalling ingest.
TIMEOUT_S = 0.5


def create_redis(url: str) -> Redis:
    """Client that decodes replies to `str`; connects lazily, so creating it never fails."""
    return Redis.from_url(url, decode_responses=True, socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S)


def get_redis(request: Request) -> Redis:
    return request.app.state.redis
