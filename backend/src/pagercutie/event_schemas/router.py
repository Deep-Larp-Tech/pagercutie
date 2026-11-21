import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES, CurrentUserDep
from pagercutie.core.deps import PaginationDep, SessionDep
from pagercutie.core.schemas import error_responses
from pagercutie.event_schemas import service
from pagercutie.event_schemas.schemas import (
    EventSchemaCreate,
    EventSchemaRead,
    SchemaValidateRequest,
    SchemaValidateResult,
)

router = APIRouter(
    prefix="/event-schemas", tags=["event-schemas"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES
)


@router.get("")
async def list_event_schemas(
    session: SessionDep,
    pagination: PaginationDep,
    name: Annotated[str | None, Query()] = None,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[EventSchemaRead]:
    """Every user may read every schema, so rules can use other teams' events."""
    return await service.list_event_schemas(session, pagination, name, team_id)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 409))
async def create_event_schema(session: SessionDep, user: CurrentUserDep, data: EventSchemaCreate) -> EventSchemaRead:
    """422 when `json_schema` is not a valid draft 2020-12 schema or `team_id` does not exist; 409 when the name +
    version exists or the name belongs to another team."""
    return await service.create_event_schema(session, user, data)


@router.get("/{schema_id}", responses=error_responses(404))
async def get_event_schema(session: SessionDep, schema_id: uuid.UUID) -> EventSchemaRead:
    return await service.get_event_schema(session, schema_id)


@router.post("/{schema_id}/validate", responses=error_responses(400, 404))
async def validate_event(
    session: SessionDep, schema_id: uuid.UUID, data: SchemaValidateRequest
) -> SchemaValidateResult:
    """Check a sample payload against the schema."""
    return await service.validate_event(session, schema_id, data)
