from datetime import UTC, datetime

import pytest
from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pagercutie.alerts.models import Alert, RunbookRun, StepRun
from pagercutie.alerts.schemas import AlertStatus, StepStatus
from pagercutie.core.enums import Severity
from pagercutie.rules.ast import Compare
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, TeamRecipient
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import Manual, RetryWorkflow
from pagercutie.teams.models import Team

pytestmark = pytest.mark.anyio

EVENT: dict[str, JsonValue] = {
    "source": "pricing",
    "schema_id": None,
    "severity": "error",
    "payload": {"workflowId": "wf-1"},
}


async def make_run(session: AsyncSession) -> RunbookRun:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    rule = Rule(
        name="Workflow failed",
        enabled=True,
        team_id=team.id,
        user_id=None,
        schema_ids=[],
        condition=Compare(op="eq", field="payload.type", value="failed"),
        dedup=Dedup(fields=[]),
        routing=Routing(recipients=[TeamRecipient(type="team", team_id=team.id)]),
        presentation=Presentation(title="Failed", severity=Severity.ERROR, colour=Colour.RED),
    )
    runbook = Runbook(
        slug="retry", title="Retry", team_id=team.id, format=RunbookFormat.TEXT, original="retry", steps=[]
    )
    session.add_all([rule, runbook])
    await session.flush()
    now = datetime.now(UTC)
    alert = Alert(
        rule_id=rule.id,
        team_id=team.id,
        fingerprint="f" * 64,
        status=AlertStatus.OPEN,
        severity=Severity.ERROR,
        colour=Colour.RED,
        title="Failed",
        fields=[],
        occurrences=1,
        first_seen_at=now,
        last_seen_at=now,
        notified_at=now,
        escalated_team_ids=[],
        payload={},
    )
    session.add(alert)
    await session.flush()
    run = RunbookRun(
        alert_id=alert.id,
        runbook_id=runbook.id,
        event=EVENT,
        steps=[
            StepRun(
                index=0,
                step=RetryWorkflow(action="retry_workflow", workflowId="{{workflowId}}"),
                status=StepStatus.SUCCEEDED,
                occurrences_at_run=3,
            ),
            StepRun(
                index=1,
                step=Manual(action="manual", text="Check"),
                status=StepStatus.AWAITING_MANUAL,
            ),
        ],
    )
    session.add(run)
    await session.flush()
    return run


async def test_event_and_occurrences_at_run_round_trip(session: AsyncSession) -> None:
    run = await make_run(session)
    session.expunge_all()

    loaded = await session.scalar(
        select(RunbookRun).where(RunbookRun.id == run.id).options(selectinload(RunbookRun.steps))
    )

    assert loaded is not None
    assert loaded.event == EVENT
    first, second = loaded.steps
    assert first.occurrences_at_run == 3
    assert second.occurrences_at_run is None


async def test_occurrences_at_run_must_be_positive(session: AsyncSession) -> None:
    run = await make_run(session)

    run.steps[0].occurrences_at_run = 0

    with pytest.raises(IntegrityError, match="occurrences_at_run_positive"):
        await session.flush()
