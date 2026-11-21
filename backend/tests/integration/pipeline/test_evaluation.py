import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.enums import Severity
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.rules.ast import Exists
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, OnCallRecipient, Presentation, Routing
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


def make_rule(
    team: Team, *, user: User | None = None, schema_ids: list[uuid.UUID] | None = None, enabled: bool = True
) -> Rule:
    return Rule(
        name="Rule",
        description=None,
        enabled=enabled,
        team_id=None if user else team.id,
        user_id=user.id if user else None,
        schema_ids=schema_ids or [],
        condition=Exists(op="exists", field="payload.workflowId"),
        dedup=Dedup(),
        routing=Routing(recipients=[OnCallRecipient(type="on_call", team_id=team.id)]),
        presentation=Presentation(title="Alert", severity=Severity.ERROR, colour=Colour.RED),
        runbook_id=None,
    )


async def test_load_rule_set_compiles_enabled_rules_with_their_source_scope(session: AsyncSession) -> None:
    payments, rates = Team(slug="payments", name="Payments"), Team(slug="rates", name="Rates")
    viewer = User(email="anna@example.com", display_name="Anna", timezone="UTC", role=GlobalRole.USER)
    admin = User(email="root@example.com", display_name="Root", timezone="UTC", role=GlobalRole.ADMIN)
    loner = User(email="solo@example.com", display_name="Solo", timezone="UTC", role=GlobalRole.USER)
    gone = User(email="gone@example.com", display_name="Gone", timezone="UTC", role=GlobalRole.ADMIN)
    gone.deleted_at = datetime(2026, 11, 20, tzinfo=UTC)
    session.add_all([payments, rates, viewer, admin, loner, gone])
    await session.flush()
    session.add_all(
        [
            Membership(team_id=payments.id, user_id=viewer.id, role=TeamRole.VIEWER),
            Membership(team_id=rates.id, user_id=viewer.id, role=TeamRole.MEMBER),
            Membership(team_id=payments.id, user_id=gone.id, role=TeamRole.LEAD),
        ]
    )
    schema_a, schema_b = uuid.uuid7(), uuid.uuid7()
    team_rule = make_rule(payments, schema_ids=[schema_a, schema_b])
    personal = make_rule(payments, user=viewer)
    admin_personal = make_rule(payments, user=admin)
    loner_personal = make_rule(payments, user=loner)
    deleted_personal = make_rule(payments, user=gone)
    disabled = make_rule(payments, enabled=False)
    session.add_all([team_rule, personal, admin_personal, loner_personal, deleted_personal, disabled])
    await session.flush()

    rules = await evaluation.load_rule_set(session)

    assert {schema: [c.rule.id for c in compiled] for schema, compiled in rules.by_schema.items()} == {
        schema_a: [team_rule.id],
        schema_b: [team_rule.id],
    }
    scopes = {c.rule.id: c.scope for c in rules.any_schema}
    assert scopes == {
        personal.id: evaluation.TeamSources(team_ids=frozenset({payments.id, rates.id})),
        admin_personal.id: evaluation.AnySource(),
        loner_personal.id: evaluation.TeamSources(team_ids=frozenset()),
        deleted_personal.id: evaluation.TeamSources(team_ids=frozenset()),
    }
    assert rules.by_schema[schema_a][0].scope == evaluation.AnySource()
    assert rules.by_schema[schema_a][0].rule.owner.type == "team"
