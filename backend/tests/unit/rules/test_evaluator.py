import json
import uuid
from pathlib import Path
from typing import get_args

import pytest
from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from pagercutie.core import templates
from pagercutie.core.enums import Severity
from pagercutie.rules import evaluator
from pagercutie.rules.ast import MAX_DEPTH, BoundedCondition, Condition

CONTRACT = Path(__file__).parents[4] / "contract"


class FixtureEvent(BaseModel):
    source: str
    schema_id: uuid.UUID | None
    severity: Severity
    payload: dict[str, JsonValue]

    def view(self) -> evaluator.EventView:
        return evaluator.event_view(
            source=self.source, schema_id=self.schema_id, severity=self.severity, payload=self.payload
        )


class RuleCase(BaseModel):
    """One case of `contract/rule-tests/*.json` (SPEC §8.1)."""

    name: str
    condition: Condition
    event: FixtureEvent
    expected: bool


class FingerprintCase(BaseModel):
    """One case of `contract/fingerprint-tests.json` (SPEC §9)."""

    name: str
    rule_id: uuid.UUID
    fields: list[str]
    event: FixtureEvent
    canonical: str
    sha256: str


class TemplateRenderCase(BaseModel):
    """One `render` case of `contract/template-tests.json` (SPEC §11.2)."""

    name: str
    template: str
    event: FixtureEvent
    expected: str


class TemplateRejectCase(BaseModel):
    """One `reject` case of `contract/template-tests.json`: the template is a syntax error."""

    name: str
    template: str


class TemplateCases(BaseModel):
    render: list[TemplateRenderCase]
    reject: list[TemplateRejectCase]


def load_rule_cases() -> list[tuple[str, RuleCase]]:
    adapter = TypeAdapter(list[RuleCase])
    return [
        (path.stem, case)
        for path in sorted((CONTRACT / "rule-tests").glob("*.json"))
        for case in adapter.validate_json(path.read_bytes())
    ]


RULE_CASES = load_rule_cases()
FINGERPRINT_CASES = TypeAdapter(list[FingerprintCase]).validate_json((CONTRACT / "fingerprint-tests.json").read_bytes())
TEMPLATE_CASES = TemplateCases.model_validate_json((CONTRACT / "template-tests.json").read_bytes())


@pytest.mark.parametrize(("group", "case"), RULE_CASES, ids=[f"{group}: {case.name}" for group, case in RULE_CASES])
def test_rule_case(group: str, case: RuleCase) -> None:
    assert evaluator.compile_condition(case.condition)(case.event.view()) is case.expected


def test_every_op_has_a_case() -> None:
    nodes = get_args(get_args(Condition.__value__)[0])
    ops = {op for node in nodes for op in get_args(node.model_fields["op"].annotation)}

    def used(condition: JsonValue) -> set[str]:
        if isinstance(condition, dict):
            own = {condition["op"]} if isinstance(condition.get("op"), str) else set()
            return own.union(*(used(value) for value in condition.values()))
        if isinstance(condition, list):
            return set().union(*(used(item) for item in condition))
        return set()

    covered = set().union(*(used(case.condition.model_dump(mode="json")) for _, case in RULE_CASES))
    assert ops - covered == set()


def test_case_names_are_unique() -> None:
    names = [(group, case.name) for group, case in RULE_CASES]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("case", FINGERPRINT_CASES, ids=[case.name for case in FINGERPRINT_CASES])
def test_fingerprint_case(case: FingerprintCase) -> None:
    view = case.event.view()
    assert evaluator.canonical_fingerprint_input(case.rule_id, case.fields, view) == case.canonical
    assert evaluator.fingerprint(case.rule_id, case.fields, view) == case.sha256


@pytest.mark.parametrize("case", TEMPLATE_CASES.render, ids=[case.name for case in TEMPLATE_CASES.render])
def test_template_render_case(case: TemplateRenderCase) -> None:
    template = templates.parse(case.template)
    assert templates.render(template, evaluator.template_resolver(case.event.view())) == case.expected


@pytest.mark.parametrize("case", TEMPLATE_CASES.reject, ids=[case.name for case in TEMPLATE_CASES.reject])
def test_template_reject_case(case: TemplateRejectCase) -> None:
    with pytest.raises(templates.TemplateSyntaxError):
        templates.parse(case.template)


def test_template_case_names_are_unique() -> None:
    names = [case.name for case in TEMPLATE_CASES.render] + [case.name for case in TEMPLATE_CASES.reject]
    assert len(names) == len(set(names))


def nested(levels: int) -> JsonValue:
    condition: JsonValue = {"op": "exists", "field": "source"}
    for _ in range(levels - 1):
        condition = {"op": "not", "arg": condition}
    return condition


def test_condition_at_max_depth_is_accepted() -> None:
    TypeAdapter(BoundedCondition).validate_json(json.dumps(nested(MAX_DEPTH)))


def test_condition_deeper_than_max_depth_is_rejected() -> None:
    with pytest.raises(ValidationError, match="nested deeper"):
        TypeAdapter(BoundedCondition).validate_json(json.dumps(nested(MAX_DEPTH + 1)))
