"""Overload answers through the real app: pool timeout (ADR-0107), in-flight cap and source rate limit (ADR-0108)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.settings import Settings
from pagercutie.main import create_app
from pagercutie.pipeline.admission import SourceRateLimit, admission_of

pytestmark = pytest.mark.anyio

# Login looks the user up in Postgres, so it needs a connection; nobody has this address.
LOGIN = {"email": "nobody@example.com"}


@asynccontextmanager
async def serve(settings: Settings) -> AsyncGenerator[tuple[FastAPI, AsyncClient]]:
    """The app without its lifespan: no loops run and the ingest caches stay unloaded."""
    app = create_app(settings)
    # `create_app` turns on structlog's logger cache; cached loggers would escape `capture_logs` in later tests.
    structlog.configure(cache_logger_on_first_use=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield app, client
    await app.state.redis.aclose()


async def test_a_request_that_finds_no_free_connection_answers_503_with_retry_after(database_url: str) -> None:
    settings = Settings(database_url=database_url, db_pool_size=1, db_pool_max_overflow=0, db_pool_timeout_seconds=0.2)
    async with serve(settings) as (app, client):
        sessionmaker: async_sessionmaker[AsyncSession] = app.state.sessionmaker
        async with sessionmaker() as holder:
            # Checks out the pool's only connection until the block ends.
            await holder.execute(text("SELECT 1"))

            response = await client.post("/auth/login", json=LOGIN)

        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
        assert response.json() == {"detail": "No database connection is free on this replica"}
        # Once the connection is back the same route works again.
        assert (await client.post("/auth/login", json=LOGIN)).status_code == 404


async def test_a_full_replica_refuses_ingest_with_503_before_reading_the_body(
    settings: Settings, redis_url: str
) -> None:
    async with serve(settings.model_copy(update={"redis_url": redis_url, "ingest_max_in_flight": 1})) as (app, client):
        with admission_of(app).in_flight.slot():
            response = await client.post("/ingest/payments", json={"type": "failed"})

        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
        assert response.json() == {"detail": "Too many ingest requests in flight on this replica"}


async def test_a_source_over_its_rate_limit_gets_429_and_others_do_not(
    settings: Settings, redis_url: str, redis: Redis
) -> None:
    limited = settings.model_copy(
        update={"redis_url": redis_url, "ingest_source_burst": 1, "ingest_source_rate_per_second": 0.25}
    )
    async with serve(limited) as (_, client):
        headers = {"Authorization": "Bearer t"}
        # Admitted; the unloaded source catalog then answers 503 without Retry-After.
        first = await client.post("/ingest/payments", json={}, headers=headers)
        second = await client.post("/ingest/payments", json={}, headers=headers)
        other_source = await client.post("/ingest/orders", json={}, headers=headers)
        other_token = await client.post("/ingest/payments", json={}, headers={"Authorization": "Bearer u"})

    assert (first.status_code, "retry-after" in first.headers) == (503, False)
    assert second.status_code == 429
    assert second.headers["retry-after"] == "4"
    assert second.json() == {"detail": "Source payments is over its rate limit"}
    assert other_source.status_code == 503
    assert other_token.status_code == 503


async def test_the_rate_limit_lets_events_through_when_redis_is_unreachable(settings: Settings) -> None:
    unreachable = settings.model_copy(update={"redis_url": "redis://127.0.0.1:1/0", "ingest_source_burst": 1})
    async with serve(unreachable) as (_, client):
        statuses = [(await client.post("/ingest/payments", json={})).status_code for _ in range(3)]

    # Past admission every time: the unloaded catalog answers.
    assert statuses == [503, 503, 503]


def test_bucket_keys_never_contain_the_token() -> None:
    assert "secret" not in SourceRateLimit.bucket("payments", "Bearer secret")
