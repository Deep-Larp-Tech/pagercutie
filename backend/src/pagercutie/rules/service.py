"""Rules: management (DOMAIN §4, §7), the builder's match preview, and the enabled rules the rule set loads (SPEC §8).

A team rule is seen by any role in its team and changed by its members and leads; a personal rule is seen by its
owner and admins and changed by its owner only. A rule the user cannot see answers 404, one they can see but not
change 403. Deleting a rule sets `deleted_at` (ADR-0091). Every write sends `NOTIFY rules_changed`. References in the
body are checked before anything is written and answer 422 with their location (ADR-0092).
"""

import uuid
from collections.abc import Sequence
from typing import assert_never

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.auth.service import CurrentUser
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.errors import FieldError, Forbidden, InvalidInput, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.event_schemas.models import EventSchema
from pagercutie.rules import evaluator
from pagercutie.rules.ast import And, Compare, Condition, Contains, Exists, Glob, In, Not, Or
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import (
    OnCallRecipient,
    Owner,
    Routing,
    RuleCreate,
    RuleRead,
    RuleTestRequest,
    RuleTestResult,
    RuleUpdate,
    TeamOwner,
    TeamRecipient,
    UserOwner,
    UserRecipient,
)
from pagercutie.runbooks.models import Runbook
from pagercutie.teams.models import Team
from pagercutie.users.models import User

_RULE = "Rule"
_ACTIVE = Rule.deleted_at.is_(None)
_NUL = "\x00"


def to_read(rule: Rule) -> RuleRead:
    return RuleRead(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        owner=_owner(rule),
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
    """Every enabled, not deleted rule, ordered by ID."""
    rules = await session.scalars(select(Rule).where(Rule.enabled, _ACTIVE).order_by(Rule.id))
    return [to_read(rule) for rule in rules]


async def list_rules(
    session: AsyncSession,
    user: CurrentUser,
    pagination: Pagination,
    team_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> list[RuleRead]:
    """Rules the user can see, ordered by ID (creation order); `team_id` and `user_id` narrow them."""
    statement = select(Rule).where(_ACTIVE).order_by(Rule.id).limit(pagination.limit).offset(pagination.offset)
    if not user.is_admin:
        statement = statement.where(or_(Rule.team_id.in_(user.team_roles.keys()), Rule.user_id == user.id))
    if team_id is not None:
        statement = statement.where(Rule.team_id == team_id)
    if user_id is not None:
        statement = statement.where(Rule.user_id == user_id)
    return [to_read(rule) for rule in await session.scalars(statement)]


async def get_rule(session: AsyncSession, user: CurrentUser, rule_id: uuid.UUID) -> RuleRead:
    return to_read(await _get_visible(session, user, rule_id))


async def create_rule(session: AsyncSession, user: CurrentUser, data: RuleCreate) -> RuleRead:
    """Members and leads of the owning team, or the owner of a personal rule."""
    _require_editable(user, data.owner)
    team_id, user_id = _owner_columns(data.owner)
    if team_id is not None and await session.get(Team, team_id) is None:
        raise NotFound("Team", team_id)
    await _require_valid(
        session,
        user,
        data.owner,
        schema_ids=data.schema_ids,
        condition=data.condition,
        routing=data.routing,
        runbook_id=data.runbook_id,
    )
    rule = Rule(
        name=data.name,
        description=data.description,
        enabled=data.enabled,
        team_id=team_id,
        user_id=user_id,
        schema_ids=data.schema_ids,
        condition=data.condition,
        dedup=data.dedup,
        routing=data.routing,
        presentation=data.presentation,
        runbook_id=data.runbook_id,
    )
    session.add(rule)
    await session.flush()
    await _notify_changed(session)
    return to_read(rule)


async def update_rule(session: AsyncSession, user: CurrentUser, rule_id: uuid.UUID, data: RuleUpdate) -> RuleRead:
    """Members and leads of the team, or the owner of a personal rule. Only the fields in the body are checked."""
    rule = await _get_editable(session, user, rule_id)
    await _require_valid(
        session,
        user,
        _owner(rule),
        schema_ids=data.schema_ids,
        condition=data.condition,
        routing=data.routing,
        runbook_id=data.runbook_id,
    )
    sent = data.model_fields_set
    if data.name is not None:
        rule.name = data.name
    if "description" in sent:
        rule.description = data.description
    if data.enabled is not None:
        rule.enabled = data.enabled
    if data.schema_ids is not None:
        rule.schema_ids = data.schema_ids
    if data.condition is not None:
        rule.condition = data.condition
    if data.dedup is not None:
        rule.dedup = data.dedup
    if data.routing is not None:
        rule.routing = data.routing
    if data.presentation is not None:
        rule.presentation = data.presentation
    if "runbook_id" in sent:
        rule.runbook_id = data.runbook_id
    await session.flush()
    await _notify_changed(session)
    return to_read(rule)


async def delete_rule(session: AsyncSession, user: CurrentUser, rule_id: uuid.UUID) -> None:
    """Members and leads of the team, or the owner of a personal rule. Soft delete: alerts keep their rule."""
    await _get_editable(session, user, rule_id)
    await session.execute(update(Rule).where(Rule.id == rule_id, _ACTIVE).values(deleted_at=func.now()))
    await _notify_changed(session)


def test_rule(data: RuleTestRequest) -> RuleTestResult:
    """Whether the condition matches the sample event; nothing is stored. `title` stays null until templates render."""
    view = evaluator.event_view(
        source=data.source, schema=None, schema_id=data.schema_id, severity=data.severity, payload=data.payload
    )
    return RuleTestResult(matched=evaluator.compile_condition(data.condition)(view))


def _owner(rule: Rule) -> Owner:
    """The owner from whichever of `team_id` and `user_id` is set."""
    match rule.team_id, rule.user_id:
        case uuid.UUID() as team_id, None:
            return TeamOwner(type="team", team_id=team_id)
        case None, uuid.UUID() as user_id:
            return UserOwner(type="user", user_id=user_id)
        case _:
            raise ValueError(f"rule {rule.id} must have exactly one owner")


def _owner_columns(owner: Owner) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """`(team_id, user_id)` of the row; exactly one is set (`one_owner`)."""
    match owner:
        case TeamOwner(team_id=team_id):
            return team_id, None
        case UserOwner(user_id=user_id):
            return None, user_id
        case _:
            assert_never(owner)


def _can_see(user: CurrentUser, owner: Owner) -> bool:
    match owner:
        case TeamOwner(team_id=team_id):
            return user.can_see_team(team_id)
        case UserOwner(user_id=user_id):
            return user.is_admin or user.id == user_id
        case _:
            assert_never(owner)


def _require_editable(user: CurrentUser, owner: Owner) -> None:
    match owner:
        case TeamOwner(team_id=team_id):
            if not user.can_edit_team(team_id):
                raise Forbidden("Only members and leads of the team can create or change its rules")
        case UserOwner(user_id=user_id):
            if user.id != user_id:
                raise Forbidden("Only its owner can create or change a personal rule")
        case _:
            assert_never(owner)


async def _notify_changed(session: AsyncSession) -> None:
    await notify(session, NotifyChannel.RULES_CHANGED)


async def _get_visible(session: AsyncSession, user: CurrentUser, rule_id: uuid.UUID) -> Rule:
    """The rule, or `NotFound` when it is missing, deleted or not visible to the user (no existence leak)."""
    rule = await session.scalar(select(Rule).where(Rule.id == rule_id, _ACTIVE))
    if rule is None or not _can_see(user, _owner(rule)):
        raise NotFound(_RULE, rule_id)
    return rule


async def _get_editable(session: AsyncSession, user: CurrentUser, rule_id: uuid.UUID) -> Rule:
    rule = await _get_visible(session, user, rule_id)
    _require_editable(user, _owner(rule))
    return rule


async def _require_valid(
    session: AsyncSession,
    user: CurrentUser,
    owner: Owner,
    *,
    schema_ids: Sequence[uuid.UUID] | None,
    condition: Condition | None,
    routing: Routing | None,
    runbook_id: uuid.UUID | None,
) -> None:
    """One `InvalidInput` listing every problem in the given parts; `None` parts are not checked (ADR-0092)."""
    errors: list[FieldError] = []
    if schema_ids is not None:
        errors += await _schema_errors(session, schema_ids)
    if condition is not None and _has_nul(condition):
        # Postgres `jsonb` cannot store `\u0000`; the insert would fail with a 500.
        errors.append(FieldError(("condition",), "Text values cannot contain NUL characters"))
    if routing is not None:
        errors += await _routing_errors(session, owner, routing)
    if runbook_id is not None:
        errors += await _runbook_errors(session, user, owner, runbook_id)
    if errors:
        raise InvalidInput(errors)


async def _schema_errors(session: AsyncSession, schema_ids: Sequence[uuid.UUID]) -> list[FieldError]:
    """Each ID names an existing event schema, once: a repeat would evaluate the rule twice per event."""
    if not schema_ids:
        return []
    known = set(await session.scalars(select(EventSchema.id).where(EventSchema.id.in_(schema_ids))))
    errors: list[FieldError] = []
    seen: set[uuid.UUID] = set()
    for index, schema_id in enumerate(schema_ids):
        if schema_id in seen:
            errors.append(FieldError(("schema_ids", index), f"Event schema {schema_id} is listed twice"))
        elif schema_id not in known:
            errors.append(FieldError(("schema_ids", index), f"Event schema {schema_id} not found"))
        seen.add(schema_id)
    return errors


async def _routing_errors(session: AsyncSession, owner: Owner, routing: Routing) -> list[FieldError]:
    """A personal rule notifies only its owner (ADR-0026); a team rule's recipients exist."""
    match owner:
        case TeamOwner():
            return await _recipient_errors(session, routing)
        case UserOwner(user_id=owner_id):
            return [
                FieldError(("routing", "recipients", index), "A personal rule can only notify its owner")
                for index, recipient in enumerate(routing.recipients)
                if not (isinstance(recipient, UserRecipient) and recipient.user_id == owner_id)
            ]
        case _:
            assert_never(owner)


async def _recipient_errors(session: AsyncSession, routing: Routing) -> list[FieldError]:
    """User recipients are active users; team and on-call recipients are existing teams, of any team (DOMAIN §4)."""
    user_ids = {r.user_id for r in routing.recipients if isinstance(r, UserRecipient)}
    team_ids = {r.team_id for r in routing.recipients if isinstance(r, TeamRecipient | OnCallRecipient)}
    active_users = (
        set(await session.scalars(select(User.id).where(User.id.in_(user_ids), User.deleted_at.is_(None))))
        if user_ids
        else set()
    )
    teams = set(await session.scalars(select(Team.id).where(Team.id.in_(team_ids)))) if team_ids else set()
    errors: list[FieldError] = []
    for index, recipient in enumerate(routing.recipients):
        match recipient:
            case UserRecipient(user_id=user_id):
                if user_id not in active_users:
                    errors.append(FieldError(("routing", "recipients", index, "user_id"), f"User {user_id} not found"))
            case TeamRecipient(team_id=team_id) | OnCallRecipient(team_id=team_id):
                if team_id not in teams:
                    errors.append(FieldError(("routing", "recipients", index, "team_id"), f"Team {team_id} not found"))
            case _:
                assert_never(recipient)
    return errors


async def _runbook_errors(
    session: AsyncSession, user: CurrentUser, owner: Owner, runbook_id: uuid.UUID
) -> list[FieldError]:
    """The runbook belongs to the rule's team; for a personal rule, to a team its owner (the user) can see."""
    loc = ("runbook_id",)
    team_id = await session.scalar(select(Runbook.team_id).where(Runbook.id == runbook_id))
    if team_id is None or not user.can_see_team(team_id):
        return [FieldError(loc, f"Runbook {runbook_id} not found")]
    match owner:
        case TeamOwner(team_id=owner_team_id):
            if team_id != owner_team_id:
                return [FieldError(loc, "The runbook belongs to another team")]
        case UserOwner():
            pass
        case _:
            assert_never(owner)
    return []


def _has_nul(condition: Condition) -> bool:
    """Whether any text value in the condition contains NUL. Field paths cannot (`FieldPath` pattern)."""
    match condition:
        case And(args=args) | Or(args=args):
            return any(_has_nul(arg) for arg in args)
        case Not(arg=arg):
            return _has_nul(arg)
        case Compare(value=value) | Contains(value=value):
            return isinstance(value, str) and _NUL in value
        case In(value=values):
            return any(isinstance(value, str) and _NUL in value for value in values)
        case Glob(value=value):
            return _NUL in value
        case Exists():
            return False
        case _:
            assert_never(condition)
