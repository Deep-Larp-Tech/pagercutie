import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pagercutie.audit.schemas import AuditEntryRead
from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES
from pagercutie.core.deps import PaginationDep
from pagercutie.core.errors import NotImplementedYet

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_audit_entries(
    pagination: PaginationDep,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
    entity_type: Annotated[str | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[AuditEntryRead]:
    """Newest first, limited to teams the current user belongs to (all for admins)."""
    raise NotImplementedYet("Audit log")
