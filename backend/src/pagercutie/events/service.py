import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from larper.core.errors import FieldError, InvalidInput, NotFound
from larper.events.models import LarpEvent
from larper.events.schemas import LarpEventCreate, LarpEventQuery, LarpEventRead
from larper.persons.elo import elo_delta
from larper.persons.models import Person
from larper.persons.service import load_person
from larper.skills.models import Skill
from larper.skills.service import load_skill

log = structlog.get_logger("events")

_WITH_RELATIONS = (selectinload(LarpEvent.person), selectinload(LarpEvent.skill))


def is_in_future(occurred_at: datetime) -> bool:
    return occurred_at > datetime.now(UTC)


def record_event(
    session: AsyncSession,
    person: Person,
    skill: Skill,
    *,
    occurred_at: datetime,
    believability: int,
    description: str,
    location: str | None,
) -> LarpEvent:
    """Add the event and move the person's Elo. Shared by the endpoint and the importer; caller flushes."""
    delta = elo_delta(person.larp_elo, skill.difficulty, believability)
    person.larp_elo += delta
    event = LarpEvent(
        person=person,
        skill=skill,
        occurred_at=occurred_at,
        believability=believability,
        description=description,
        location=location,
        elo_delta=delta,
    )
    session.add(event)
    return event


async def list_events(session: AsyncSession, query: LarpEventQuery) -> list[LarpEventRead]:
    stmt = (
        select(LarpEvent)
        .options(*_WITH_RELATIONS)
        .order_by(LarpEvent.occurred_at.desc(), LarpEvent.id)
        .limit(query.limit)
        .offset(query.offset)
    )
    if query.person_id is not None:
        stmt = stmt.where(LarpEvent.person_id == query.person_id)
    if query.skill_id is not None:
        stmt = stmt.where(LarpEvent.skill_id == query.skill_id)
    return [LarpEventRead.model_validate(e) for e in await session.scalars(stmt)]


async def get_event(session: AsyncSession, event_id: uuid.UUID) -> LarpEventRead:
    event = await session.scalar(select(LarpEvent).options(*_WITH_RELATIONS).where(LarpEvent.id == event_id))
    if event is None:
        raise NotFound("LARPing event", event_id)
    return LarpEventRead.model_validate(event)


async def create_event(session: AsyncSession, data: LarpEventCreate) -> LarpEventRead:
    if is_in_future(data.occurred_at):
        raise InvalidInput([FieldError(("occurred_at",), "must not be in the future")])
    # Row lock: two concurrent events for one person must not overwrite each other's Elo change.
    person = await load_person(session, data.person_id, for_update=True)
    skill = await load_skill(session, data.skill_id)
    event = record_event(
        session,
        person,
        skill,
        occurred_at=data.occurred_at,
        believability=data.believability,
        description=data.description,
        location=data.location,
    )
    await session.flush()
    log.info("events.created", message="LARPing event recorded", event_id=event.id, elo_delta=event.elo_delta)
    return LarpEventRead.model_validate(event)
