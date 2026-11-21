import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Owner, RuleRead, TeamOwner, UserOwner


def to_read(rule: Rule) -> RuleRead:
    """The rule as a DTO; `owner` comes from whichever of `team_id` and `user_id` is set."""
    owner: Owner
    match rule.team_id, rule.user_id:
        case uuid.UUID() as team_id, None:
            owner = TeamOwner(type="team", team_id=team_id)
        case None, uuid.UUID() as user_id:
            owner = UserOwner(type="user", user_id=user_id)
        case _:
            raise ValueError(f"rule {rule.id} must have exactly one owner")  # the `one_owner` check forbids this
    return RuleRead(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        owner=owner,
        schema_ids=rule.schema_ids,
        condition=rule.condition,
        dedup=rule.dedup,
        routing=rule.routing,
        presentation=rule.presentation,
        runbook_id=rule.runbook_id,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


async def list_enabled(session: AsyncSession) -> list[RuleRead]:
    """Every enabled rule, ordered by ID."""
    rules = await session.scalars(select(Rule).where(Rule.enabled).order_by(Rule.id))
    return [to_read(rule) for rule in rules]
