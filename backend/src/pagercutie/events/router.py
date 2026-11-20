import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from larper.core.deps import SessionDep
from larper.core.schemas import error_responses
from larper.events import service
from larper.events.schemas import LarpEventCreate, LarpEventQuery, LarpEventRead

router = APIRouter(prefix="/larp-events", tags=["larp-events"])


@router.get("")
async def list_larp_events(session: SessionDep, query: Annotated[LarpEventQuery, Query()]) -> list[LarpEventRead]:
    return await service.list_events(session, query)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 404))
async def create_larp_event(data: LarpEventCreate, session: SessionDep) -> LarpEventRead:
    return await service.create_event(session, data)


@router.get("/{event_id}", responses=error_responses(404))
async def get_larp_event(event_id: uuid.UUID, session: SessionDep) -> LarpEventRead:
    return await service.get_event(session, event_id)
