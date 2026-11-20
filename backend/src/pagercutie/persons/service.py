import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.errors import Conflict, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.persons.models import Person
from pagercutie.persons.schemas import PersonCreate, PersonRead, PersonUpdate

log = structlog.get_logger("persons")


@asynccontextmanager
async def _unique_name(session: AsyncSession) -> AsyncGenerator[None]:
    # A savepoint keeps the surrounding transaction usable after the unique violation.
    try:
        async with session.begin_nested():
            yield
    except IntegrityError as e:
        raise Conflict("A person with this first and last name already exists") from e


async def load_person(session: AsyncSession, person_id: uuid.UUID, *, for_update: bool = False) -> Person:
    """Model-returning helper for other services; never hand the result to a router."""
    person = await session.get(Person, person_id, with_for_update=for_update)
    if person is None:
        raise NotFound("Person", person_id)
    return person


async def list_persons(session: AsyncSession, pagination: Pagination) -> list[PersonRead]:
    """Leaderboard order: highest Elo first."""
    persons = await session.scalars(
        select(Person).order_by(Person.larp_elo.desc(), Person.id).limit(pagination.limit).offset(pagination.offset)
    )
    return [PersonRead.model_validate(p) for p in persons]


async def get_person(session: AsyncSession, person_id: uuid.UUID) -> PersonRead:
    return PersonRead.model_validate(await load_person(session, person_id))


async def create_person(session: AsyncSession, data: PersonCreate) -> PersonRead:
    person = Person(**data.model_dump())
    async with _unique_name(session):
        session.add(person)
    log.info("persons.created", message="Person created", person_id=person.id)
    return PersonRead.model_validate(person)


async def update_person(session: AsyncSession, person_id: uuid.UUID, data: PersonUpdate) -> PersonRead:
    person = await load_person(session, person_id)
    async with _unique_name(session):
        for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
            setattr(person, field, value)
    log.info("persons.updated", message="Person updated", person_id=person.id)
    return PersonRead.model_validate(person)


async def delete_person(session: AsyncSession, person_id: uuid.UUID) -> None:
    person = await load_person(session, person_id)
    try:
        async with session.begin_nested():
            await session.delete(person)
    except IntegrityError as e:
        raise Conflict("Person has LARPing events and cannot be deleted") from e
    log.info("persons.deleted", message="Person deleted", person_id=person_id)
