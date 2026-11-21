import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES, CurrentUserDep
from pagercutie.core.deps import PaginationDep, SessionDep
from pagercutie.core.schemas import error_responses
from pagercutie.rules import service
from pagercutie.rules.schemas import RuleCreate, RuleRead, RuleTestRequest, RuleTestResult, RuleUpdate

router = APIRouter(prefix="/rules", tags=["rules"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_rules(
    session: SessionDep,
    user: CurrentUserDep,
    pagination: PaginationDep,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
    user_id: Annotated[uuid.UUID | None, Query(description="Personal rules of this user")] = None,
) -> list[RuleRead]:
    """Rules visible to the current user, optionally filtered by owner, ordered by creation. Team rules are visible to
    any role in the team; personal rules to their owner and admins."""
    return await service.list_rules(session, user, pagination, team_id, user_id)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 404))
async def create_rule(session: SessionDep, user: CurrentUserDep, data: RuleCreate) -> RuleRead:
    """Members and leads of the owning team; a personal rule only for yourself, and it notifies only you. Unknown
    schemas, recipients or runbooks answer 422."""
    return await service.create_rule(session, user, data)


@router.post("/test", responses=error_responses(400))
async def test_rule(data: RuleTestRequest) -> RuleTestResult:
    """Evaluate a condition against a sample event without saving anything."""
    return service.test_rule(data)


@router.get("/{rule_id}", responses=error_responses(404))
async def get_rule(session: SessionDep, user: CurrentUserDep, rule_id: uuid.UUID) -> RuleRead:
    return await service.get_rule(session, user, rule_id)


@router.patch("/{rule_id}", responses=error_responses(400, 403, 404))
async def update_rule(session: SessionDep, user: CurrentUserDep, rule_id: uuid.UUID, data: RuleUpdate) -> RuleRead:
    """Members and leads of the team, or the owner of a personal rule."""
    return await service.update_rule(session, user, rule_id, data)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404))
async def delete_rule(session: SessionDep, user: CurrentUserDep, rule_id: uuid.UUID) -> None:
    """Members and leads of the team, or the owner of a personal rule. Existing alerts keep their rendered content."""
    await service.delete_rule(session, user, rule_id)
