import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.sse import EventSourceResponse

from pagercutie.alerts.schemas import (
    AlertEvent,
    AlertRead,
    AlertStatus,
    DeliveryRead,
    ResolveRequest,
    RunbookRunRead,
    StepDecision,
)
from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES
from pagercutie.core.deps import PaginationDep
from pagercutie.core.enums import Severity
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses, json_error_responses

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_alerts(
    pagination: PaginationDep,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[list[AlertStatus] | None, Query()] = None,
    severity: Annotated[list[Severity] | None, Query()] = None,
) -> list[AlertRead]:
    """Alerts visible to the current user, most recently seen first."""
    raise NotImplementedYet("Alerts")


async def _alert_stream_not_implemented() -> None:
    # A dependency, so it answers 501 before EventSourceResponse has sent 200; drop it when implementing the stream.
    raise NotImplementedYet("Alert stream")


@router.get(
    "/stream",
    response_class=EventSourceResponse,
    responses=json_error_responses(401),
    dependencies=[Depends(_alert_stream_not_implemented)],
)
async def stream_alerts(team_id: Annotated[uuid.UUID | None, Query()] = None) -> AsyncIterator[AlertEvent]:
    """Live feed: created and updated alerts visible to the current user. Load `GET /alerts` first."""
    return
    yield


@router.get("/{alert_id}", responses=error_responses(404))
async def get_alert(alert_id: uuid.UUID) -> AlertRead:
    raise NotImplementedYet("Alerts")


@router.post("/{alert_id}/acknowledge", responses=error_responses(403, 404, 409))
async def acknowledge_alert(alert_id: uuid.UUID) -> AlertRead:
    """409 unless the alert is open."""
    raise NotImplementedYet("Alert acknowledge")


@router.post("/{alert_id}/resolve", responses=error_responses(403, 404, 409))
async def resolve_alert(alert_id: uuid.UUID, data: ResolveRequest) -> AlertRead:
    """409 when already resolved."""
    raise NotImplementedYet("Alert resolve")


@router.get("/{alert_id}/deliveries", responses=error_responses(404))
async def list_alert_deliveries(alert_id: uuid.UUID) -> list[DeliveryRead]:
    raise NotImplementedYet("Deliveries")


@router.get("/{alert_id}/runbook-run", responses=error_responses(404))
async def get_runbook_run(alert_id: uuid.UUID) -> RunbookRunRead | None:
    """null when the alert's rule has no runbook."""
    raise NotImplementedYet("Runbook runs")


@router.post("/{alert_id}/runbook-run/steps/{index}/decision", responses=error_responses(403, 404, 409))
async def decide_step(alert_id: uuid.UUID, index: int, data: StepDecision) -> RunbookRunRead:
    """409 when the decision does not fit the step's status; 403 for approvals by non-leads."""
    raise NotImplementedYet("Step decisions")
