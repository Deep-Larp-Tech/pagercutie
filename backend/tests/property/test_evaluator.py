import re
import uuid

from hypothesis import given
from hypothesis import strategies as st
from pydantic import JsonValue, TypeAdapter

from pagercutie.core.enums import Severity
from pagercutie.rules import evaluator
from pagercutie.rules.ast import Condition

CONDITION = TypeAdapter(Condition)

json_values: st.SearchStrategy[JsonValue] = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(),
    lambda children: st.lists(children, max_size=4) | st.dictionaries(st.sampled_from("abc0"), children, max_size=4),
    max_leaves=12,
)
scalars = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text()
fields = st.sampled_from(["source", "schema_id", "severity", "payload"]) | st.lists(
    st.sampled_from(["a", "b", "c", "0", "1"]), min_size=1, max_size=3
).map(lambda segments: ".".join(["payload", *segments]))

predicates = st.one_of(
    st.builds(
        lambda op, f, v: {"op": op, "field": f, "value": v},
        st.sampled_from(["eq", "ne", "gt", "gte", "lt", "lte", "contains"]),
        fields,
        scalars,
    ),
    st.builds(
        lambda op, f, v: {"op": op, "field": f, "value": v},
        st.sampled_from(["in", "not_in"]),
        fields,
        st.lists(scalars, min_size=1, max_size=3),
    ),
    st.builds(lambda f, v: {"op": "glob", "field": f, "value": v}, fields, st.text(alphabet="ab*?.[", max_size=8)),
    st.builds(lambda f: {"op": "exists", "field": f}, fields),
)
conditions = st.recursive(
    predicates,
    lambda children: st.one_of(
        st.builds(lambda args: {"op": "and", "args": args}, st.lists(children, min_size=1, max_size=3)),
        st.builds(lambda args: {"op": "or", "args": args}, st.lists(children, min_size=1, max_size=3)),
        st.builds(lambda arg: {"op": "not", "arg": arg}, children),
    ),
    max_leaves=8,
)
views = st.builds(
    lambda severity, payload: evaluator.event_view(
        source="src", schema_id=uuid.UUID(int=1), severity=severity, payload=payload
    ),
    st.sampled_from(Severity),
    st.dictionaries(st.sampled_from("abc0"), json_values, max_size=4),
)


@given(conditions, views)
def test_a_predicate_returns_a_bool_for_any_event(raw: dict[str, JsonValue], view: evaluator.EventView) -> None:
    predicate = evaluator.compile_condition(CONDITION.validate_python(raw))
    assert isinstance(predicate(view), bool)


@given(conditions, views)
def test_not_negates(raw: dict[str, JsonValue], view: evaluator.EventView) -> None:
    condition = CONDITION.validate_python(raw)
    negated = CONDITION.validate_python({"op": "not", "arg": raw})
    assert evaluator.compile_condition(negated)(view) is not evaluator.compile_condition(condition)(view)


@given(st.lists(fields, max_size=4), views)
def test_a_fingerprint_is_hex_sha256_for_any_event(paths: list[str], view: evaluator.EventView) -> None:
    digest = evaluator.fingerprint(uuid.UUID(int=2), paths, view)
    assert len(digest) == 64
    assert int(digest, 16) >= 0


@given(st.text(alphabet="ab*?", max_size=8), st.text(alphabet="ab", max_size=10))
def test_glob_agrees_with_a_regex(pattern: str, text: str) -> None:
    regex = "".join(".*" if ch == "*" else "." if ch == "?" else re.escape(ch) for ch in pattern)
    assert evaluator.glob(pattern, text) is (re.fullmatch(regex, text, re.DOTALL) is not None)
