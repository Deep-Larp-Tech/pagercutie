"""Entrypoints of the rule evaluation stage."""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.errors import NotImplementedYet
from pagercutie.pipeline.messages import Event, Match
from pagercutie.rules.schemas import RuleRead


@dataclass(frozen=True)
class RuleSet:
    """Snapshot of the enabled rules, cached per replica and swapped whole on reload (SPEC §8)."""

    # Rules limited to some schemas, by schema ID.
    by_schema: Mapping[uuid.UUID, Sequence[RuleRead]]
    # Rules with empty `schema_ids`, evaluated for every event.
    any_schema: Sequence[RuleRead]


async def load_rule_set(session: AsyncSession) -> RuleSet:
    """Load and compile the enabled rules; rerun on `NOTIFY rules_changed` (SPEC §5.3)."""
    raise NotImplementedYet("Rule set loading")


def evaluate(event: Event, rules: RuleSet) -> list[Match]:
    """One `Match` per rule whose condition holds for `event`. Total: never raises on any event (SPEC §8.1)."""
    raise NotImplementedYet("Rule evaluation")


def fingerprint(rule: RuleRead, event: Event) -> str:
    """Hex SHA-256 of the rule ID and the values of `rule.dedup.fields` in `event` (SPEC §9)."""
    raise NotImplementedYet("Fingerprint")
