import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES
from pagercutie.core.deps import PaginationDep
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses
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
    pagination: PaginationDep,
    name: Annotated[str | None, Query()] = None,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[EventSchemaRead]:
    """Every user may read every schema, so rules can use other teams' events."""
    raise NotImplementedYet("Event schemas")


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 409))
async def create_event_schema(data: EventSchemaCreate) -> EventSchemaRead:
    """422 when `json_schema` is not a valid draft 2020-12 schema; 409 when the name + version exists."""
    raise NotImplementedYet("Event schemas")


@router.get("/{schema_id}", responses=error_responses(404))
async def get_event_schema(schema_id: uuid.UUID) -> EventSchemaRead:
    raise NotImplementedYet("Event schemas")


@router.post("/{schema_id}/validate", responses=error_responses(400, 404))
async def validate_event(schema_id: uuid.UUID, data: SchemaValidateRequest) -> SchemaValidateResult:
    """Check a sample payload against the schema."""
    raise NotImplementedYet("Event schema validation")
