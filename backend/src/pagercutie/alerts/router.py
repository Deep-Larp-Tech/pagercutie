import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.sse import EventSourceResponse

from pagercutie.alerts import service
from pagercutie.alerts.schemas import (
    AlertEvent,
    AlertRead,
    AlertStatus,
    DeliveryRead,
    DeliveryStatus,
    ResolveRequest,
    RunbookRunRead,
    StepDecision,
)
from pagercutie.auth import service as auth_service
from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES, CurrentUserDep
from pagercutie.core.broadcast import Subscription
from pagercutie.core.deps import AlertChangesDep, PaginationDep, ResolvedWindowsDep, SessionDep, SessionmakerDep
from pagercutie.core.enums import Channel, Severity
from pagercutie.core.errors import Unauthenticated
from pagercutie.core.schemas import error_responses, json_error_responses

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)
me_router = APIRouter(prefix="/me", tags=["alerts"], responses=AUTHENTICATED_RESPONSES)
deliveries_router = APIRouter(
    prefix="/deliveries", tags=["alerts"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES
)


@router.get("")
async def list_alerts(
    user: CurrentUserDep,
    session: SessionDep,
    pagination: PaginationDep,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[list[AlertStatus] | None, Query()] = None,
    severity: Annotated[list[Severity] | None, Query()] = None,
) -> list[AlertRead]:
    """Alerts visible to the current user, most recently seen first."""
    return await service.list_alerts(session, user, pagination, team_id, status, severity)


async def _alert_changes(alert_changes: AlertChangesDep) -> AsyncIterator[Subscription]:
    # A dependency, so the subscription exists before the 200: a change committed after the client's `onopen` reload
    # of GET /alerts (ADR-0054) is never missed. Request scope keeps it until the stream ends.
    async with alert_changes.subscribe() as subscription:
        yield subscription


@router.get("/stream", response_class=EventSourceResponse, responses=json_error_responses(401))
async def stream_alerts(
    user: CurrentUserDep,
    sessionmaker: SessionmakerDep,
    changes: Annotated[Subscription, Depends(_alert_changes)],
    team_id: Annotated[uuid.UUID | None, Query()] = None,
) -> AsyncIterator[AlertEvent]:
    """Live feed: created and updated alerts visible to the current user. Load `GET /alerts` first."""
    async for batch in changes.batches():
        # A session per batch: one for the whole stream would hold a pool connection per open tab.
        async with sessionmaker() as session:
            try:
                actor = await auth_service.authenticate_token_hash(session, user.session_token_hash)
                events = await service.feed_events(session, actor, batch, team_id)
            except Unauthenticated, service.FeedReloadNeeded:
                return
        for event in events:
            yield event


@router.get("/{alert_id}", responses=error_responses(404))
async def get_alert(user: CurrentUserDep, session: SessionDep, alert_id: uuid.UUID) -> AlertRead:
    return await service.get_alert(session, user, alert_id)


@router.post("/{alert_id}/acknowledge", responses=error_responses(403, 404, 409))
async def acknowledge_alert(user: CurrentUserDep, session: SessionDep, alert_id: uuid.UUID) -> AlertRead:
    """409 unless the alert is open."""
    return await service.acknowledge_alert(session, user, alert_id)


@router.post("/{alert_id}/resolve", responses=error_responses(400, 403, 404, 409))
async def resolve_alert(
    user: CurrentUserDep, session: SessionDep, windows: ResolvedWindowsDep, alert_id: uuid.UUID, data: ResolveRequest
) -> AlertRead:
    """409 when already resolved."""
    return await service.resolve_alert(session, user, alert_id, data, windows)


@router.get("/{alert_id}/deliveries", responses=error_responses(404))
async def list_alert_deliveries(user: CurrentUserDep, session: SessionDep, alert_id: uuid.UUID) -> list[DeliveryRead]:
    """Newest first."""
    return await service.list_alert_deliveries(session, user, alert_id)


@router.get("/{alert_id}/runbook-run", responses=error_responses(404))
async def get_runbook_run(user: CurrentUserDep, session: SessionDep, alert_id: uuid.UUID) -> RunbookRunRead | None:
    """null when the alert's rule has no runbook."""
    return await service.get_runbook_run(session, user, alert_id)


@router.post("/{alert_id}/runbook-run/steps/{index}/decision", responses=error_responses(400, 403, 404, 409))
async def decide_step(
    user: CurrentUserDep, session: SessionDep, alert_id: uuid.UUID, index: int, data: StepDecision
) -> RunbookRunRead:
    """409 when the decision does not fit the step's status; 403 for approvals by non-leads."""
    return await service.decide_step(session, user, alert_id, index, data)


@me_router.get("/messages")
async def list_my_messages(
    user: CurrentUserDep,
    session: SessionDep,
    pagination: PaginationDep,
    channel: Annotated[list[Channel] | None, Query()] = None,
) -> list[DeliveryRead]:
    """The current user's deliveries, newest first, optionally only on the given channels."""
    return await service.list_user_deliveries(session, user.id, pagination, channel)


@deliveries_router.get("")
async def list_deliveries(
    session: SessionDep,
    user: CurrentUserDep,
    pagination: PaginationDep,
    channel: Annotated[list[Channel] | None, Query()] = None,
    status: Annotated[list[DeliveryStatus] | None, Query()] = None,
) -> list[DeliveryRead]:
    """Deliveries on every channel for alerts the current user can see (admins: all), newest first.

    Feeds the notifications debug drawer for the simulated channels (`DEL-4`, ADR-0073).
    """
    return await service.list_deliveries(session, user, pagination, channel, status)
