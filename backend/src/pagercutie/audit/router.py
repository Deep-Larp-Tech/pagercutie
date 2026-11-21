from typing import Annotated

from fastapi import APIRouter, Query

from pagercutie.audit import service
from pagercutie.audit.schemas import AuditEntryRead, AuditQuery
from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES, CurrentUserDep
from pagercutie.core.deps import PaginationDep, SessionDep

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_audit_entries(
    session: SessionDep,
    user: CurrentUserDep,
    pagination: PaginationDep,
    filters: Annotated[AuditQuery, Query()],
) -> list[AuditEntryRead]:
    """Newest first, limited to teams the current user belongs to (all for admins)."""
    return await service.list_audit_entries(session, user, pagination, filters)
