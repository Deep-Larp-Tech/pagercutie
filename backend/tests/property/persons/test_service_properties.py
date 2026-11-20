import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from larper.persons import service
from larper.persons.schemas import PersonCreate

pytestmark = pytest.mark.anyio

# Any non-NUL text Postgres can store, not just ASCII.
names = st.text(alphabet=st.characters(exclude_categories=["Cs"], exclude_characters="\x00"), min_size=1, max_size=100)
persons = st.builds(PersonCreate, first_name=names, last_name=names, larp_elo=st.integers(0, 5000))


# The `session` fixture is shared by all examples, so each example rolls back its own savepoint.
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=persons)
async def test_create_then_get_round_trips(session: AsyncSession, data: PersonCreate) -> None:
    savepoint = await session.begin_nested()
    try:
        created = await service.create_person(session, data)
        fetched = await service.get_person(session, created.id)

        assert fetched == created
        assert fetched.model_dump(exclude={"id"}) == data.model_dump()
    finally:
        await savepoint.rollback()
