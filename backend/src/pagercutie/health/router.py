from fastapi import APIRouter

from pagercutie.core.deps import SessionDep
from pagercutie.health import service
from pagercutie.health.schemas import HealthRead

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def get_health(session: SessionDep) -> HealthRead:
    return await service.check_health(session)
