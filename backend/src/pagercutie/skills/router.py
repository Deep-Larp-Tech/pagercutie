import uuid

from fastapi import APIRouter, status

from larper.core.deps import PaginationDep, SessionDep
from larper.core.schemas import error_responses
from larper.skills import service
from larper.skills.schemas import SkillCreate, SkillRead, SkillUpdate

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("")
async def list_skills(session: SessionDep, pagination: PaginationDep) -> list[SkillRead]:
    return await service.list_skills(session, pagination)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 409))
async def create_skill(data: SkillCreate, session: SessionDep) -> SkillRead:
    return await service.create_skill(session, data)


@router.get("/{skill_id}", responses=error_responses(404))
async def get_skill(skill_id: uuid.UUID, session: SessionDep) -> SkillRead:
    return await service.get_skill(session, skill_id)


@router.patch("/{skill_id}", responses=error_responses(400, 404, 409))
async def update_skill(skill_id: uuid.UUID, data: SkillUpdate, session: SessionDep) -> SkillRead:
    return await service.update_skill(session, skill_id, data)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(404, 409))
async def delete_skill(skill_id: uuid.UUID, session: SessionDep) -> None:
    await service.delete_skill(session, skill_id)
