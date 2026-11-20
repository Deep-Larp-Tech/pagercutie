import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from factories import a_person, a_skill, an_event
from pagercutie.core.errors import Conflict, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.persons import service
from pagercutie.persons.schemas import PersonCreate, PersonUpdate

pytestmark = pytest.mark.anyio


async def test_create_person_starts_at_default_elo(session: AsyncSession) -> None:
    person = await service.create_person(session, PersonCreate(first_name="Stas", last_name="Yurich"))

    assert person.larp_elo == 1000
    assert await service.get_person(session, person.id) == person


async def test_duplicate_name_conflicts_and_keeps_transaction_usable(session: AsyncSession) -> None:
    await a_person(session)

    with pytest.raises(Conflict):
        await a_person(session)

    assert await a_person(session, last_name="Yurievich")  # the savepoint protected the transaction


async def test_update_changes_only_given_fields(session: AsyncSession) -> None:
    person = await a_person(session, larp_elo=1200)

    updated = await service.update_person(session, person.id, PersonUpdate(last_name="the Feigner"))

    assert (updated.first_name, updated.last_name, updated.larp_elo) == ("Stas", "the Feigner", 1200)


async def test_get_missing_person_raises_not_found(session: AsyncSession) -> None:
    with pytest.raises(NotFound):
        await service.get_person(session, uuid.uuid7())


async def test_person_with_events_cannot_be_deleted(session: AsyncSession) -> None:
    person = await a_person(session)
    await an_event(session, person, await a_skill(session))

    with pytest.raises(Conflict):
        await service.delete_person(session, person.id)


async def test_list_is_a_leaderboard(session: AsyncSession) -> None:
    low = await a_person(session, first_name="Low", larp_elo=900)
    high = await a_person(session, first_name="High", larp_elo=1500)

    persons = await service.list_persons(session, Pagination())

    assert [p.id for p in persons] == [high.id, low.id]
