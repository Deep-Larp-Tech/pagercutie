from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.health.schemas import HealthRead


async def check_health(session: AsyncSession) -> HealthRead:
    await session.execute(text("SELECT 1"))
    return HealthRead(status="ok", database="ok")
