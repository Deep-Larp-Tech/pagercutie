"""Ingest admission control (ADR-0108): a cap on ingest requests in flight per replica and a rate limit per source.

Outside the stage packages: it guards the ingest routes in `adapters.py` before the orchestrator runs.
"""

import hashlib
from collections.abc import AsyncGenerator, AsyncIterator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import assert_never

import redis.asyncio as redis
import structlog
from fastapi import Depends, FastAPI
from fastapi.requests import HTTPConnection
from opentelemetry import metrics

from pagercutie.core.errors import Overloaded, RateLimited
from pagercutie.core.settings import Settings
from pagercutie.core.token_bucket import Empty, Taken, TokenBuckets

log = structlog.get_logger("ingest")

_meter = metrics.get_meter("pagercutie.ingest")
_refused = _meter.create_counter(
    "ingest_refused_total", description="Ingest requests refused before processing, by reason (in_flight, rate_limit)"
)

# Seconds a producer refused for lack of in-flight slots should wait; one slot frees within a request's latency.
IN_FLIGHT_RETRY_AFTER_S = 1


class InFlight:
    """Counts ingest requests in flight on this replica and refuses one over `limit` at once, without queueing."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._count = 0

    @property
    def count(self) -> int:
        """Requests holding a slot now."""
        return self._count

    @contextmanager
    def slot(self) -> Generator[None]:
        """Hold one slot for the block; `Overloaded` (503) when all are taken."""
        if self._count >= self._limit:
            _refused.add(1, {"reason": "in_flight"})
            raise Overloaded("Too many ingest requests in flight on this replica", IN_FLIGHT_RETRY_AFTER_S)
        self._count += 1
        try:
            yield
        finally:
            self._count -= 1


class SourceRateLimit:
    """A token bucket per source and credential in Redis, shared by every replica; fails open like the throttle.

    The bucket key includes a digest of the `Authorization` header, so requests with a wrong token cannot drain the
    bucket of the producer that holds the right one.
    """

    def __init__(self, client: redis.Redis, burst: int, rate_per_second: float) -> None:
        self._buckets = TokenBuckets(client, "ingest", burst, 1 / rate_per_second)

    @staticmethod
    def bucket(source_slug: str, authorization: str | None) -> str:
        """The bucket of one source and credential, `{slug}:{sha256 prefix of the Authorization header}`."""
        digest = hashlib.sha256((authorization or "").encode()).hexdigest()[:16]
        return f"{source_slug}:{digest}"

    async def check(self, source_slug: str, authorization: str | None) -> None:
        """Take one token; `RateLimited` (429) when the bucket is empty. Lets the event through without Redis."""
        try:
            taken = await self._buckets.take(self.bucket(source_slug, authorization))
        except redis.RedisError:
            log.warning(
                "ingest.rate_limit_unavailable", message="Redis unreachable, not rate limiting", source=source_slug
            )
            return
        match taken:
            case Taken():
                return
            case Empty(retry_after_s=seconds):
                _refused.add(1, {"reason": "rate_limit"})
                raise RateLimited(source_slug, seconds)
            case _:
                assert_never(taken)


@dataclass(frozen=True)
class Admission:
    """The admission checks of one replica, built once by `create_app`."""

    in_flight: InFlight
    rate_limit: SourceRateLimit

    @classmethod
    def from_settings(cls, settings: Settings, client: redis.Redis) -> Admission:
        return cls(
            in_flight=InFlight(settings.ingest_max_in_flight),
            rate_limit=SourceRateLimit(client, settings.ingest_source_burst, settings.ingest_source_rate_per_second),
        )

    @asynccontextmanager
    async def admit(self, source_slug: str, authorization: str | None) -> AsyncGenerator[None]:
        """Hold an in-flight slot and take a source token for the block; raises `Overloaded` or `RateLimited`."""
        with self.in_flight.slot():
            await self.rate_limit.check(source_slug, authorization)
            yield


def admission_of(app: FastAPI) -> Admission:
    """The replica's `Admission`, set by `create_app`."""
    admission = app.state.admission
    if not isinstance(admission, Admission):
        raise TypeError("app.state.admission is not an Admission; create the app with create_app")
    return admission


async def admit_ingest(connection: HTTPConnection, source_slug: str) -> AsyncIterator[None]:
    """FastAPI dependency of the webhook ingest route: 503 or 429 before the body is read."""
    async with admission_of(connection.app).admit(source_slug, connection.headers.get("authorization")):
        yield


INGEST_ADMISSION = Depends(admit_ingest)

# The statuses admission adds to an ingest route, for its OpenAPI description.
INGEST_RESPONSES: dict[int | str, dict[str, object]] = {
    429: {"description": "The source is over its rate limit; retry after `Retry-After` seconds"},
    503: {"description": "The replica is overloaded or its caches are not loaded; retry after `Retry-After` seconds"},
}
