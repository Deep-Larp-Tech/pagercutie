import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from larper.core.errors import Conflict, NotFound
from larper.core.schemas import Pagination
from larper.skills.models import Skill
from larper.skills.schemas import SkillCreate, SkillRead, SkillUpdate

log = structlog.get_logger("skills")


@asynccontextmanager
async def _unique_name(session: AsyncSession) -> AsyncGenerator[None]:
    try:
        async with session.begin_nested():
            yield
    except IntegrityError as e:
        raise Conflict("A skill with this name already exists") from e


async def load_skill(session: AsyncSession, skill_id: uuid.UUID) -> Skill:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise NotFound("Skill", skill_id)
    return skill


async def list_skills(session: AsyncSession, pagination: Pagination) -> list[SkillRead]:
    skills = await session.scalars(select(Skill).order_by(Skill.name).limit(pagination.limit).offset(pagination.offset))
    return [SkillRead.model_validate(s) for s in skills]


async def get_skill(session: AsyncSession, skill_id: uuid.UUID) -> SkillRead:
    return SkillRead.model_validate(await load_skill(session, skill_id))


async def create_skill(session: AsyncSession, data: SkillCreate) -> SkillRead:
    skill = Skill(**data.model_dump())
    async with _unique_name(session):
        session.add(skill)
    log.info("skills.created", message="Skill created", skill_id=skill.id)
    return SkillRead.model_validate(skill)


async def update_skill(session: AsyncSession, skill_id: uuid.UUID, data: SkillUpdate) -> SkillRead:
    skill = await load_skill(session, skill_id)
    async with _unique_name(session):
        for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
            setattr(skill, field, value)
    log.info("skills.updated", message="Skill updated", skill_id=skill.id)
    return SkillRead.model_validate(skill)


async def delete_skill(session: AsyncSession, skill_id: uuid.UUID) -> None:
    skill = await load_skill(session, skill_id)
    try:
        async with session.begin_nested():
            await session.delete(skill)
    except IntegrityError as e:
        raise Conflict("Skill has LARPing events and cannot be deleted") from e
    log.info("skills.deleted", message="Skill deleted", skill_id=skill_id)
