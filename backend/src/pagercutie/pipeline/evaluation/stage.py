"""Entrypoints of the rule evaluation stage."""

import time
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import assert_never

from opentelemetry import metrics
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.pipeline.messages import Event, Match
from pagercutie.rules import evaluator
from pagercutie.rules import service as rules
from pagercutie.rules.schemas import RuleRead, TeamOwner, UserOwner
from pagercutie.teams.models import Membership
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

_eval_duration = metrics.get_meter("pagercutie.evaluation").create_histogram(
    "rule_eval_duration_seconds",
    unit="s",
    description="Time to evaluate every candidate rule for one event",
    # Evaluation is in-memory and sub-millisecond; the SDK default buckets start at 5 and put every sample in the first.
    explicit_bucket_boundaries_advisory=[0.0001, 0.00025, 0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1],
)


@dataclass(frozen=True)
class AnySource:
    """The rule sees events from every source: team rules, and personal rules of admins."""


@dataclass(frozen=True)
class TeamSources:
    """A personal rule sees only events from sources owned by its user's teams, in any role (DOMAIN.md §4)."""

    team_ids: frozenset[uuid.UUID]


type SourceScope = AnySource | TeamSources


@dataclass(frozen=True)
class CompiledRule:
    rule: RuleRead
    matches: evaluator.Predicate
    scope: SourceScope


@dataclass(frozen=True)
class RuleSet:
    """Snapshot of the enabled rules, cached per replica and swapped whole on reload (SPEC §8)."""

    # Rules limited to some schemas, by schema ID.
    by_schema: Mapping[uuid.UUID, Sequence[CompiledRule]]
    # Rules with empty `schema_ids`, evaluated for every event.
    any_schema: Sequence[CompiledRule]


async def load_rule_set(session: AsyncSession) -> RuleSet:
    """Load and compile the enabled rules; rerun on `NOTIFY rules_changed` or `access_changed` (SPEC §5.3)."""
    enabled = await rules.list_enabled(session)
    owners = {rule.owner.user_id for rule in enabled if isinstance(rule.owner, UserOwner)}
    scopes = await _personal_scopes(session, owners)
    by_schema: defaultdict[uuid.UUID, list[CompiledRule]] = defaultdict(list)
    any_schema: list[CompiledRule] = []
    for rule in enabled:
        compiled = CompiledRule(
            rule=rule, matches=evaluator.compile_condition(rule.condition), scope=_scope(rule, scopes)
        )
        for schema_id in rule.schema_ids:
            by_schema[schema_id].append(compiled)
        if not rule.schema_ids:
            any_schema.append(compiled)
    return RuleSet(by_schema=dict(by_schema), any_schema=any_schema)


def evaluate(event: Event, rules: RuleSet) -> list[Match]:
    """One `Match` per rule whose condition holds for `event`, ordered by rule ID. Total (SPEC §8.1).

    The order keeps replicas that upsert the same alerts in one transaction from deadlocking on each other.
    """
    started = time.perf_counter()
    view = _view(event)
    candidates = [*rules.by_schema.get(event.schema_id, ()), *rules.any_schema]
    matched = sorted(
        (c.rule for c in candidates if _sees(c.scope, event) and c.matches(view)), key=lambda rule: rule.id
    )
    _eval_duration.record(time.perf_counter() - started)
    return [Match(event=event, rule=rule, fingerprint=_fingerprint(rule, view)) for rule in matched]


def fingerprint(rule: RuleRead, event: Event) -> str:
    """Hex SHA-256 of the rule ID and the values of `rule.dedup.fields` in `event` (SPEC §9)."""
    return _fingerprint(rule, _view(event))


def _fingerprint(rule: RuleRead, view: evaluator.EventView) -> str:
    return evaluator.fingerprint(rule.id, rule.dedup.fields, view)


def _view(event: Event) -> evaluator.EventView:
    return evaluator.event_view(
        source=event.source,
        schema=event.schema_name,
        schema_id=event.schema_id,
        severity=event.severity,
        payload=event.payload,
    )


def _sees(scope: SourceScope, event: Event) -> bool:
    match scope:
        case AnySource():
            return True
        case TeamSources(team_ids=team_ids):
            return event.team_id in team_ids
        case _:
            assert_never(scope)


def _scope(rule: RuleRead, personal: Mapping[uuid.UUID, SourceScope]) -> SourceScope:
    match rule.owner:
        case TeamOwner():
            return AnySource()
        case UserOwner(user_id=user_id):
            return personal[user_id]
        case _:
            assert_never(rule.owner)


async def _personal_scopes(session: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceScope]:
    """The sources each personal rule owner can see: all for an admin, their teams' for a user, none once the
    user is soft-deleted, since their memberships are kept but they no longer have access (DOMAIN.md §4, ADR-0057).
    """
    if not user_ids:
        return {}
    active = User.id.in_(user_ids) & User.deleted_at.is_(None)
    admins = set(await session.scalars(select(User.id).where(active, User.role == GlobalRole.ADMIN)))
    teams: defaultdict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for user_id, team_id in await session.execute(
        select(Membership.user_id, Membership.team_id).join(User, User.id == Membership.user_id).where(active)
    ):
        teams[user_id].add(team_id)
    return {
        user_id: AnySource() if user_id in admins else TeamSources(team_ids=frozenset(teams[user_id]))
        for user_id in user_ids
    }
