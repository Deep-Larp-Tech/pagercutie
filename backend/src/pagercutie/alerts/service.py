import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Delivery
from pagercutie.alerts.schemas import DeliveryRead
from pagercutie.core.enums import Channel
from pagercutie.core.schemas import Pagination


async def list_user_deliveries(
    session: AsyncSession, user_id: uuid.UUID, pagination: Pagination, channels: list[Channel] | None
) -> list[DeliveryRead]:
    """The user's deliveries, newest first, optionally only on these channels."""
    query = select(Delivery).where(Delivery.user_id == user_id)
    if channels:
        query = query.where(Delivery.channel.in_(channels))
    query = query.order_by(Delivery.created_at.desc(), Delivery.id.desc())
    query = query.limit(pagination.limit).offset(pagination.offset)
    return [DeliveryRead.model_validate(d) for d in await session.scalars(query)]
