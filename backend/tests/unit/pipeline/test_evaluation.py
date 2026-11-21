import uuid
from datetime import UTC, datetime

from pagercutie.core.enums import Severity
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.pipeline.messages import Event
from pagercutie.rules import evaluator
from pagercutie.rules.ast import Compare, Condition, Exists
from pagercutie.rules.schemas import RuleRead

NOW = datetime(2026, 11, 21, tzinfo=UTC)
SCHEMA = uuid.uuid7()
OTHER_SCHEMA = uuid.uuid7()
SOURCE_TEAM = uuid.uuid7()
OTHER_TEAM = uuid.uuid7()
EVENT = Event(
    event_id=uuid.uuid7(),
    source="payments-api",
    source_id=uuid.uuid7(),
    team_id=SOURCE_TEAM,
    schema_id=SCHEMA,
    severity=Severity.CRITICAL,
    received_at=NOW,
    payload={"workflowId": "wf-1", "amount": 10},
)


def make_rule(
    condition: Condition, *, rule_id: uuid.UUID | None = None, dedup_fields: list[str] | None = None
) -> RuleRead:
    return RuleRead.model_validate(
        {
            "id": rule_id or uuid.uuid7(),
            "name": "Rule",
            "description": None,
            "enabled": True,
            "owner": {"type": "team", "team_id": SOURCE_TEAM},
            "schema_ids": [],
            "condition": condition,
            "dedup": {"fields": dedup_fields or [], "window_s": 300},
            "routing": {"recipients": [{"type": "on_call", "team_id": SOURCE_TEAM}]},
            "presentation": {"title": "Alert", "severity": "critical", "colour": "red"},
            "runbook_id": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
    )


def compiled(rule: RuleRead, scope: evaluation.SourceScope | None = None) -> evaluation.CompiledRule:
    return evaluation.CompiledRule(
        rule=rule, matches=evaluator.compile_condition(rule.condition), scope=scope or evaluation.AnySource()
    )


MATCHING = Exists(op="exists", field="payload.workflowId")
FAILING = Compare(op="gt", field="payload.amount", value=100)


def test_evaluates_rules_for_the_event_schema_and_any_schema() -> None:
    for_schema, for_any, for_other = make_rule(MATCHING), make_rule(MATCHING), make_rule(MATCHING)
    rules = evaluation.RuleSet(
        by_schema={SCHEMA: [compiled(for_schema)], OTHER_SCHEMA: [compiled(for_other)]},
        any_schema=[compiled(for_any)],
    )

    matched = {match.rule.id for match in evaluation.evaluate(EVENT, rules)}

    assert matched == {for_schema.id, for_any.id}


def test_skips_rules_whose_condition_is_false() -> None:
    rules = evaluation.RuleSet(by_schema={}, any_schema=[compiled(make_rule(FAILING))])

    assert evaluation.evaluate(EVENT, rules) == []


def test_personal_rule_matches_only_sources_of_its_owners_teams() -> None:
    member, outsider = make_rule(MATCHING), make_rule(MATCHING)
    rules = evaluation.RuleSet(
        by_schema={},
        any_schema=[
            compiled(member, evaluation.TeamSources(team_ids=frozenset({SOURCE_TEAM}))),
            compiled(outsider, evaluation.TeamSources(team_ids=frozenset({OTHER_TEAM}))),
        ],
    )

    assert [match.rule.id for match in evaluation.evaluate(EVENT, rules)] == [member.id]


def test_matches_are_ordered_by_rule_id() -> None:
    ids = sorted(uuid.uuid4() for _ in range(5))
    rules = evaluation.RuleSet(
        by_schema={SCHEMA: [compiled(make_rule(MATCHING, rule_id=i)) for i in ids[::2]]},
        any_schema=[compiled(make_rule(MATCHING, rule_id=i)) for i in ids[1::2]],
    )

    assert [match.rule.id for match in evaluation.evaluate(EVENT, rules)] == ids


def test_match_carries_the_dedup_fingerprint() -> None:
    rule = make_rule(MATCHING, dedup_fields=["payload.workflowId"])
    rules = evaluation.RuleSet(by_schema={}, any_schema=[compiled(rule)])

    [match] = evaluation.evaluate(EVENT, rules)

    assert match.fingerprint == evaluation.fingerprint(rule, EVENT)
    assert match.fingerprint == evaluator.fingerprint(
        rule.id,
        ["payload.workflowId"],
        evaluator.event_view(source="x", schema_id=None, severity=Severity.DEBUG, payload={"workflowId": "wf-1"}),
    )
