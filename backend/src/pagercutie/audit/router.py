import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pagercutie.audit import service
from pagercutie.audit.schemas import AuditEntryRead
from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES, CurrentUserDep
from pagercutie.core.deps import PaginationDep, SessionDep
from pagercutie.core.schemas import ShortText

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_audit_entries(
    session: SessionDep,
    user: CurrentUserDep,
    pagination: PaginationDep,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
    entity_type: Annotated[ShortText | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[AuditEntryRead]:
    """Newest first, limited to teams the current user belongs to (all for admins)."""
    return await service.list_audit_entries(session, user, pagination, team_id, entity_type, entity_id)
