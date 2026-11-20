import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES
from pagercutie.core.deps import PaginationDep
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses
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
    pagination: PaginationDep, team_id: Annotated[uuid.UUID | None, Query()] = None
) -> list[RunbookRead]:
    raise NotImplementedYet("Runbooks")


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(403, 404, 409))
async def create_runbook(data: RunbookCreate) -> RunbookRead:
    """422 when a `structured` runbook is not valid YAML of the step model."""
    raise NotImplementedYet("Runbooks")


@router.post("/parse")
async def parse_runbook(data: RunbookParseRequest) -> RunbookParseResult:
    """Preview how a runbook text would be parsed, without saving it."""
    raise NotImplementedYet("Runbook parsing")


@router.get("/{runbook_id}", responses=error_responses(404))
async def get_runbook(runbook_id: uuid.UUID) -> RunbookRead:
    raise NotImplementedYet("Runbooks")


@router.patch("/{runbook_id}", responses=error_responses(403, 404))
async def update_runbook(runbook_id: uuid.UUID, data: RunbookUpdate) -> RunbookRead:
    """Runs already started keep the steps they started with."""
    raise NotImplementedYet("Runbooks")


@router.delete("/{runbook_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404))
async def delete_runbook(runbook_id: uuid.UUID) -> None:
    raise NotImplementedYet("Runbooks")
