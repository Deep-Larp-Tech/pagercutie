from fastapi import APIRouter

from larper.core.deps import SessionDep
from larper.health import service
from larper.health.schemas import HealthRead

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def get_health(session: SessionDep) -> HealthRead:
    return await service.check_health(session)
