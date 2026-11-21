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
    """Sources of the teams the current user can see, ordered by slug."""
    return await service.list_sources(session, user, pagination, team_id)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 404, 409))
async def create_source(session: SessionDep, user: CurrentUserDep, data: SourceCreate) -> SourceRead:
    """Members and leads of the team. The source accepts events once it has a token (`POST /sources/{id}/token`)."""
    return await service.create_source(session, user, data)


@router.get("/{source_id}", responses=error_responses(404))
async def get_source(session: SessionDep, user: CurrentUserDep, source_id: uuid.UUID) -> SourceRead:
    return await service.get_source(session, user, source_id)


@router.patch("/{source_id}", responses=error_responses(400, 403, 404))
async def update_source(
    session: SessionDep, user: CurrentUserDep, source_id: uuid.UUID, data: SourceUpdate
) -> SourceRead:
    """Members and leads of the team."""
    return await service.update_source(session, user, source_id, data)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404))
async def delete_source(session: SessionDep, user: CurrentUserDep, source_id: uuid.UUID) -> None:
    """Members and leads of the team."""
    await service.delete_source(session, user, source_id)


@router.post("/{source_id}/token", responses=error_responses(403, 404))
async def rotate_source_token(session: SessionDep, user: CurrentUserDep, source_id: uuid.UUID) -> SourceTokenRead:
    """Generate a new ingest token. Each replica rejects the previous one once the change notification reaches it; a
    replica that lost its notification connection answers 503 to ingest until it reloads (ADR-0048)."""
    return await service.rotate_token(session, user, source_id)
