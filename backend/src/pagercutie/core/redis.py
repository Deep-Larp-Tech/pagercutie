"""The Redis client every replica shares state through: dedup windows, occurrence counters, throttles (SPEC §5.2)."""

import uuid
from typing import Protocol

from fastapi import Request
from redis.asyncio import Redis

TIMEOUT_S = 0.5

# How long a resolved alert's marker lives: the longest dedup window (`rules.schemas.Dedup.window_s`), so it
# outlives every window that can still hold the alert's ID (ADR-0101).
RESOLVED_MARKER_TTL_S = 86_400
RESOLVED_MARKER_PREFIX = "dedup:resolved:"


def create_redis(url: str) -> Redis:
    """Client that decodes replies to `str`; connects lazily, so creating it never fails."""
    return Redis.from_url(url, decode_responses=True, socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S)


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def dedup_window_key(rule_id: uuid.UUID, fingerprint: str) -> str:
    """Redis key of a dedup window, `dedup:{rule_id}:{fingerprint}`."""
    return f"dedup:{rule_id}:{fingerprint}"


def resolved_marker_key(alert_id: uuid.UUID) -> str:
    """Redis key that marks an alert as resolved for the dedup windows, `dedup:resolved:{alert_id}`."""
    return f"{RESOLVED_MARKER_PREFIX}{alert_id}"


class ResolvedWindows(Protocol):
    """The part of the dedup window store that resolving an alert uses (ADR-0101).

    Declared here because entity packages may not import `pipeline`; `pipeline.dedup.WindowStore` extends it.
    """

    async def mark_resolved(self, alert_id: uuid.UUID, rule_id: uuid.UUID, fingerprint: str) -> None:
        """Mark the alert resolved and delete its window if the window holds it, in one atomic step.

        From then on no claim counts a match on the alert in Redis: the match takes the Postgres path, which opens a
        new alert once the resolve has committed. Never raises for Redis errors; it logs them, and a window left in
        place counts on the resolved alert until it expires (the counter flush reports those counts).
        """
        ...


def get_resolved_windows(request: Request) -> ResolvedWindows:
    """The replica's window store, set by `create_app`."""
    return request.app.state.windows
