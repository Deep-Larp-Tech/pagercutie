import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES, CurrentUserDep
from pagercutie.core.deps import PaginationDep, SessionDep
from pagercutie.core.schemas import error_responses
from pagercutie.runbooks import service
from pagercutie.runbooks.schemas import (
    RunbookCreate,
    RunbookParseRequest,
    RunbookParseResult,
    RunbookRead,
    RunbookUpdate,
)

router = APIRouter(prefix="/runbooks", tags=["runbooks"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_runbooks(
    session: SessionDep,
    user: CurrentUserDep,
    pagination: PaginationDep,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[RunbookRead]:
    """Runbooks of the user's teams; an admin sees all. Deleted runbooks are left out."""
    return await service.list_runbooks(session, user, pagination, team_id)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 404, 409))
async def create_runbook(session: SessionDep, user: CurrentUserDep, data: RunbookCreate) -> RunbookRead:
    """Member or lead of the owning team, or an admin. 404 when the team does not exist. 422 when a `structured`
    runbook is not valid YAML of the step model; its `runbook:` name may differ from `slug`, which wins."""
    return await service.create_runbook(session, user, data)


@router.post("/parse", responses=error_responses(400))
async def parse_runbook(data: RunbookParseRequest) -> RunbookParseResult:
    """Preview how a runbook text would be parsed, without saving it. 422 as for create."""
    return service.parse_runbook_preview(data)


@router.get("/{runbook_id}", responses=error_responses(404))
async def get_runbook(session: SessionDep, user: CurrentUserDep, runbook_id: uuid.UUID) -> RunbookRead:
    """404 also for a deleted runbook or one of a team the user does not belong to."""
    return await service.get_runbook(session, user, runbook_id)


@router.patch("/{runbook_id}", responses=error_responses(400, 403, 404))
async def update_runbook(
    session: SessionDep, user: CurrentUserDep, runbook_id: uuid.UUID, data: RunbookUpdate
) -> RunbookRead:
    """Member or lead of the owning team, or an admin. Runs already started keep the steps they started with."""
    return await service.update_runbook(session, user, runbook_id, data)


@router.delete("/{runbook_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404))
async def delete_runbook(session: SessionDep, user: CurrentUserDep, runbook_id: uuid.UUID) -> None:
    """Member or lead of the owning team, or an admin. Soft delete; rules that used the runbook are detached."""
    await service.delete_runbook(session, user, runbook_id)
