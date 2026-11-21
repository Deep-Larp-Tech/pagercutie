"""UI channel: a `NOTIFY` that makes every replica's SSE feed refresh (UI-1, SPEC §10)."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.db import NotifyChannel
from pagercutie.pipeline.dispatch.stage import DeliveryJob, SendFailed, Sent


class UiAdapter:
    """The delivery row is the notification; sending announces it on `alert_changed` with the alert ID as payload."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def send(self, job: DeliveryJob) -> Sent | SendFailed:
        try:
            async with self._sessionmaker() as session, session.begin():
                await session.execute(select(func.pg_notify(NotifyChannel.ALERT_CHANGED, str(job.alert_id))))
        except (SQLAlchemyError, OSError) as exc:
            return SendFailed(f"{type(exc).__name__}: {exc}")
        return Sent(at=datetime.now(UTC))
