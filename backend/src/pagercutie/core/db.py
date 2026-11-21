from collections.abc import AsyncIterator
from enum import StrEnum

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session, session.begin():
        yield session


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    """For endpoints that own their transaction, e.g. streams that must commit before their last event."""
    return request.app.state.sessionmaker


class NotifyChannel(StrEnum):
    """Postgres `LISTEN/NOTIFY` channels that carry cross-replica signals (SPEC §5.3)."""

    SCHEMAS_CHANGED = "schemas_changed"
    SOURCES_CHANGED = "sources_changed"
    RULES_CHANGED = "rules_changed"
    ALERT_CHANGED = "alert_changed"
    DELIVERIES_PENDING = "deliveries_pending"


async def notify(session: AsyncSession, channel: NotifyChannel, payload: str = "") -> None:
    """Queue a notification on `channel`; Postgres delivers it when the session's transaction commits.

    `payload` is at most 8000 bytes; Postgres folds identical channel and payload pairs within one transaction."""
    await session.execute(select(func.pg_notify(channel, payload)))
