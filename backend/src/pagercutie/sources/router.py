import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES
from pagercutie.core.deps import PaginationDep
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses
from pagercutie.sources.schemas import SourceCreate, SourceRead, SourceTokenRead, SourceUpdate

router = APIRouter(prefix="/sources", tags=["sources"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_sources(
    pagination: PaginationDep, team_id: Annotated[uuid.UUID | None, Query()] = None
) -> list[SourceRead]:
    raise NotImplementedYet("Sources")


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(403, 404, 409))
async def create_source(data: SourceCreate) -> SourceRead:
    raise NotImplementedYet("Sources")


@router.get("/{source_id}", responses=error_responses(404))
async def get_source(source_id: uuid.UUID) -> SourceRead:
    raise NotImplementedYet("Sources")


@router.patch("/{source_id}", responses=error_responses(403, 404))
async def update_source(source_id: uuid.UUID, data: SourceUpdate) -> SourceRead:
    raise NotImplementedYet("Sources")


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404))
async def delete_source(source_id: uuid.UUID) -> None:
    raise NotImplementedYet("Sources")


@router.post("/{source_id}/token", responses=error_responses(403, 404))
async def rotate_source_token(source_id: uuid.UUID) -> SourceTokenRead:
    """Generate a new ingest token; the previous one stops working immediately."""
    raise NotImplementedYet("Source tokens")
