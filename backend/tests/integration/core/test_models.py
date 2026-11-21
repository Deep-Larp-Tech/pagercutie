import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.enums import Severity
from pagercutie.rules.ast import And, Compare, Glob
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, TeamRecipient
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import RetryWorkflow
from pagercutie.teams.models import Team
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


async def test_dto_columns_round_trip_through_jsonb(session: AsyncSession) -> None:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    condition = And(
        op="and",
        args=[
            Compare(op="eq", field="payload.type", value=None),
            Glob(op="glob", field="source", value="pricing-*"),
        ],
    )
    rule = Rule(
        name="Workflow failed",
        enabled=True,
        team_id=team.id,
        user_id=None,
        schema_ids=[],
        condition=condition,
        dedup=Dedup(fields=["payload.workflowId"]),
        routing=Routing(recipients=[TeamRecipient(type="team", team_id=team.id)]),
        presentation=Presentation(title="{{payload.workflowId}} failed", severity=Severity.ERROR, colour=Colour.ORANGE),
    )
    session.add(rule)
    await session.flush()
    session.expunge_all()

    loaded = await session.scalar(select(Rule).where(Rule.id == rule.id))

    assert loaded is not None
    assert loaded.condition == condition
    assert loaded.routing.recipients == [TeamRecipient(type="team", team_id=team.id)]
    assert loaded.dedup.window_s == 300


async def test_steps_keep_their_yaml_aliases_and_none_is_sql_null(session: AsyncSession) -> None:
    team = Team(slug="settlement", name="Settlement")
    session.add(team)
    await session.flush()
    step = RetryWorkflow.model_validate({"action": "retry_workflow", "workflowId": "{{workflowId}}", "if": "x fails"})
    runbook = Runbook(
        slug="settlement-timeout",
        title="Settlement timeout",
        team_id=team.id,
        format=RunbookFormat.TEXT,
        original="retry it",
        attach=None,
        steps=[step],
    )
    session.add(runbook)
    await session.flush()

    row = (
        await session.execute(
            text("SELECT attach IS NULL AS attach_null, steps -> 0 AS step FROM runbooks WHERE id = :id"),
            {"id": runbook.id},
        )
    ).one()

    assert row.attach_null
    assert row.step["if"] == "x fails"
    assert row.step["workflowId"] == "{{workflowId}}"


async def test_enums_are_stored_by_value(session: AsyncSession) -> None:
    user = User(email="anna@example.com", display_name="Anna", timezone="Europe/Prague", role=GlobalRole.ADMIN)
    session.add(user)
    await session.flush()

    row = (
        await session.execute(
            text("SELECT role, pg_typeof(role)::text AS type FROM users WHERE id = :id"), {"id": user.id}
        )
    ).one()

    assert (row.role, row.type) == ("admin", "global_role")
    assert user.channel_preferences.rules == []


async def test_severity_type_sorts_like_the_python_enum(session: AsyncSession) -> None:
    labels = await session.scalar(text("SELECT enum_range(NULL::severity)::text[]"))

    assert labels == [severity.value for severity in Severity]


async def test_updated_at_is_loaded_after_an_update(session: AsyncSession) -> None:
    team = Team(slug="ops", name="Ops")
    session.add(team)
    await session.flush()
    runbook = Runbook(
        slug="restart", title="Restart", team_id=team.id, format=RunbookFormat.TEXT, original="restart", steps=[]
    )
    session.add(runbook)
    await session.flush()

    runbook.title = "Restart the service"
    await session.flush()

    # Expired and lazily refreshed would raise MissingGreenlet under asyncio.
    assert runbook.updated_at is not None
