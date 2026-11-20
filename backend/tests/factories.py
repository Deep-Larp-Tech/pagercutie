from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from larper.events import service as events_service
from larper.events.schemas import LarpEventCreate, LarpEventRead
from larper.persons import service as persons_service
from larper.persons.schemas import PersonCreate, PersonRead
from larper.skills import service as skills_service
from larper.skills.schemas import SkillCreate, SkillRead


async def a_person(session: AsyncSession, first_name: str = "Stas", last_name: str = "Yurich", **kw: int) -> PersonRead:
    return await persons_service.create_person(session, PersonCreate(first_name=first_name, last_name=last_name, **kw))


async def a_skill(session: AsyncSession, name: str = "Feigning knowledge", difficulty: int = 2) -> SkillRead:
    return await skills_service.create_skill(session, SkillCreate(name=name, difficulty=difficulty))


async def an_event(
    session: AsyncSession,
    person: PersonRead,
    skill: SkillRead,
    *,
    believability: int = 10,
    occurred_at: datetime = datetime(2026, 1, 1, tzinfo=UTC),
) -> LarpEventRead:
    return await events_service.create_event(
        session,
        LarpEventCreate(
            person_id=person.id,
            skill_id=skill.id,
            occurred_at=occurred_at,
            believability=believability,
            description="Said 'tis a known issue' with composure",
        ),
    )
