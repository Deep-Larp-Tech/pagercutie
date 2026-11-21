import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.event_schemas.models import EventSchema
from pagercutie.event_schemas.service import latest_team_schemas
from pagercutie.teams.models import Team

pytestmark = pytest.mark.anyio


async def test_latest_team_schemas_returns_the_highest_version_of_each_team_schema(session: AsyncSession) -> None:
    team, other = Team(slug="payments", name="Payments"), Team(slug="search", name="Search")
    session.add_all([team, other])
    await session.flush()
    payment_v2 = EventSchema(name="payment", version=2, team_id=team.id, json_schema={"required": ["amount"]})
    refund = EventSchema(name="refund", version=1, team_id=team.id, json_schema={"type": "object"})
    session.add_all(
        [
            EventSchema(name="payment", version=1, team_id=team.id, json_schema={"type": "object"}),
            payment_v2,
            refund,
            EventSchema(name="query", version=1, team_id=other.id, json_schema={"type": "object"}),
        ]
    )
    await session.flush()

    schemas = await latest_team_schemas(session, team.id)

    assert [(s.id, s.name, s.json_schema) for s in schemas] == [
        (payment_v2.id, "payment", {"required": ["amount"]}),
        (refund.id, "refund", {"type": "object"}),
    ]
