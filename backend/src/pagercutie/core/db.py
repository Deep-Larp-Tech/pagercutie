from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Protocol, runtime_checkable

from asyncpg.exceptions import UniqueViolationError
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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


@runtime_checkable
class _ConstraintError(Protocol):
    # asyncpg sets the error fields at runtime, so its classes do not declare them.
    constraint_name: str | None


def violates_unique(error: IntegrityError, constraint: str) -> bool:
    """Whether `error` is a unique violation of `constraint`."""
    cause = error.driver_exception
    return (
        isinstance(cause, UniqueViolationError)
        and isinstance(cause, _ConstraintError)
        and cause.constraint_name == constraint
    )
