import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pagercutie.auth.deps import AUTHENTICATED, AUTHENTICATED_RESPONSES
from pagercutie.core.deps import PaginationDep
from pagercutie.core.errors import NotImplementedYet
from pagercutie.core.schemas import error_responses
from pagercutie.rules.schemas import RuleCreate, RuleRead, RuleTestRequest, RuleTestResult, RuleUpdate

router = APIRouter(prefix="/rules", tags=["rules"], dependencies=AUTHENTICATED, responses=AUTHENTICATED_RESPONSES)


@router.get("")
async def list_rules(
    pagination: PaginationDep,
    team_id: Annotated[uuid.UUID | None, Query()] = None,
    user_id: Annotated[uuid.UUID | None, Query(description="Personal rules of this user")] = None,
) -> list[RuleRead]:
    """Rules visible to the current user, optionally filtered by owner."""
    raise NotImplementedYet("Rules")


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 403, 404))
async def create_rule(data: RuleCreate) -> RuleRead:
    raise NotImplementedYet("Rules")


@router.post("/test", responses=error_responses(400))
async def test_rule(data: RuleTestRequest) -> RuleTestResult:
    """Evaluate a condition against a sample event without saving anything."""
    raise NotImplementedYet("Rule test")


@router.get("/{rule_id}", responses=error_responses(404))
async def get_rule(rule_id: uuid.UUID) -> RuleRead:
    raise NotImplementedYet("Rules")


@router.patch("/{rule_id}", responses=error_responses(400, 403, 404))
async def update_rule(rule_id: uuid.UUID, data: RuleUpdate) -> RuleRead:
    raise NotImplementedYet("Rules")


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403, 404))
async def delete_rule(rule_id: uuid.UUID) -> None:
    """Existing alerts keep their rendered content."""
    raise NotImplementedYet("Rules")
