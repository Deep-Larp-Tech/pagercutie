import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES, CurrentUserDep
from pagercutie.core.deps import PaginationDep, SessionDep
from pagercutie.core.schemas import error_responses
from pagercutie.sources import service
from pagercutie.sources.schemas import SourceCreate, SourceRead, SourceTokenRead, SourceUpdate

router = APIRouter(prefix="/sources", tags=["sources"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_sources(
    session: SessionDep,
    user: CurrentUserDep,
    pagination: PaginationDep,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[SourceRead]:
    """Sources of the user's teams; an admin sees all."""
    return await service.list_sources(session, user, pagination, team_id)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 404, 409))
async def create_source(session: SessionDep, user: CurrentUserDep, data: SourceCreate) -> SourceRead:
    """Member or lead of the owning team, or an admin. 404 when the team or a referenced schema does not exist."""
    return await service.create_source(session, user, data)


@router.get("/{source_id}", responses=error_responses(404))
async def get_source(session: SessionDep, user: CurrentUserDep, source_id: uuid.UUID) -> SourceRead:
    """404 also for a source of a team the user does not belong to."""
    return await service.get_source(session, user, source_id)


@router.patch("/{source_id}", responses=error_responses(400, 403, 404))
async def update_source(
    session: SessionDep, user: CurrentUserDep, source_id: uuid.UUID, data: SourceUpdate
) -> SourceRead:
    """Member or lead of the owning team, or an admin."""
    return await service.update_source(session, user, source_id, data)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404))
async def delete_source(session: SessionDep, user: CurrentUserDep, source_id: uuid.UUID) -> None:
    """Member or lead of the owning team, or an admin."""
    await service.delete_source(session, user, source_id)


@router.post("/{source_id}/token", responses=error_responses(403, 404))
async def rotate_source_token(session: SessionDep, user: CurrentUserDep, source_id: uuid.UUID) -> SourceTokenRead:
    """Generate a new ingest token; the previous one stops working immediately."""
    return await service.rotate_source_token(session, user, source_id)
