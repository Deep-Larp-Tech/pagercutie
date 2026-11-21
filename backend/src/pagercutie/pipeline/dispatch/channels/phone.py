"""Simulated phone-call channel (DEL-4, ADR-0013): the delivery row is the record the notifications drawer shows."""

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.pipeline.dispatch.channels.contacts import mask_phone, phone_of
from pagercutie.pipeline.dispatch.stage import DeliveryJob, SendFailed, Sent

log = structlog.get_logger("phone")


class PhoneAdapter:
    """Succeeds for users with a phone number; a missing number is a permanent failure."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def send(self, job: DeliveryJob) -> Sent | SendFailed:
        phone = await phone_of(self._sessionmaker, job.user_id)
        if isinstance(phone, SendFailed):
            return phone
        log.info(
            "channel.phone.sent", message="Simulated call placed", delivery_id=job.delivery_id, phone=mask_phone(phone)
        )
        return Sent(at=datetime.now(UTC))
