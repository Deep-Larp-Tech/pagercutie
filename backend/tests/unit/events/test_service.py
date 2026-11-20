from datetime import UTC, datetime

import pytest
import time_machine
from sqlalchemy.ext.asyncio import AsyncSession

from factories import a_person, a_skill, an_event
from pagercutie.core.errors import InvalidInput, NotFound
from pagercutie.events import service
from pagercutie.events.schemas import LarpEventCreate, LarpEventQuery
from pagercutie.persons import service as persons_service

pytestmark = pytest.mark.anyio


async def test_event_moves_elo_and_records_delta(session: AsyncSession) -> None:
    person = await a_person(session)  # 1000
    skill = await a_skill(session, difficulty=2)  # rated 1000: an even match

    event = await an_event(session, person, skill, believability=10)

    assert event.elo_delta == 16
    assert event.person.larp_elo == 1016
    assert (await persons_service.get_person(session, person.id)).larp_elo == 1016


@time_machine.travel(datetime(2026, 6, 1, 12, tzinfo=UTC), tick=False)
async def test_event_in_the_future_is_rejected(session: AsyncSession) -> None:
    person, skill = await a_person(session), await a_skill(session)
    data = LarpEventCreate(
        person_id=person.id,
        skill_id=skill.id,
        occurred_at=datetime(2026, 6, 1, 12, 0, 1, tzinfo=UTC),
        believability=5,
        description="Prophesied a green build",
    )

    with pytest.raises(InvalidInput) as raised:
        await service.create_event(session, data)

    assert [e.loc for e in raised.value.errors] == [("occurred_at",)]


async def test_event_for_missing_skill_raises_not_found(session: AsyncSession) -> None:
    person = await a_person(session)
    data = LarpEventCreate(
        person_id=person.id,
        skill_id=person.id,  # a valid UUID, but no skill has it
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        believability=5,
        description="Imaginary skill",
    )

    with pytest.raises(NotFound):
        await service.create_event(session, data)


async def test_list_filters_by_person(session: AsyncSession) -> None:
    skill = await a_skill(session)
    stas, other = await a_person(session), await a_person(session, first_name="Other")
    mine = await an_event(session, stas, skill)
    await an_event(session, other, skill)

    events = await service.list_events(session, LarpEventQuery(person_id=stas.id))

    assert [e.id for e in events] == [mine.id]
