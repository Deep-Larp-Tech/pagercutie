import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.integration.pipeline.test_evaluation import make_rule

from fake_windows import FakeWindows
from pagercutie.pipeline.ingest.stage import SchemaCache, team_schema_query
from pagercutie.pipeline.state import IngestState, rule_set_reloader
from pagercutie.teams.models import Team

pytestmark = pytest.mark.anyio


async def test_rule_set_reloader_loads_the_enabled_rules(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    enabled, disabled = make_rule(team), make_rule(team, enabled=False)
    session.add_all([enabled, disabled])
    await session.commit()
    state = IngestState(
        sessionmaker=sessionmaker, window_store=FakeWindows(), schemas=SchemaCache(team_schema_query(sessionmaker))
    )

    await rule_set_reloader(state)()

    assert state.rule_set is not None
    assert [c.rule.id for c in state.rule_set.any_schema] == [enabled.id]
