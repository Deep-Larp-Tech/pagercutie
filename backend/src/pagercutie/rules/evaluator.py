"""Rule conditions compiled to predicates over a normalised event, the dedup fingerprint, and how template paths
resolve against the event (SPEC §8.1, §9, §11.2).

Pure and total: no predicate, fingerprint or resolver raises on any event. The cases in `contract/rule-tests/`,
`contract/fingerprint-tests.json` and `contract/template-tests.json` pin the behaviour for every implementation.
"""

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, TypeGuard, assert_never

from pydantic import JsonValue

from pagercutie.core.enums import SEVERITY_ORDER, Severity
from pagercutie.core.fields import MISSING, Missing
from pagercutie.core.templates import Resolver
from pagercutie.rules.ast import And, Compare, Condition, Contains, Exists, Glob, In, Not, Or, Scalar

# The event as rules see it: `source`, `schema_id`, `severity` and `payload` (SPEC §4.3).
type EventView = Mapping[str, JsonValue]
type Predicate = Callable[[EventView], bool]

_SEVERITY_RANK = {severity.value: rank for severity, rank in SEVERITY_ORDER.items()}


def event_view(
    *, source: str, schema_id: uuid.UUID | None, severity: Severity, payload: dict[str, JsonValue]
) -> EventView:
    """The root that field paths resolve against."""
    return {
        "source": source,
        "schema_id": None if schema_id is None else str(schema_id),
        "severity": severity.value,
        "payload": payload,
    }


def lookup(event: EventView, path: Sequence[str]) -> JsonValue | Missing:
    """The value at the split field path, or `MISSING`. ASCII-digit segments index into arrays."""
    head, *rest = path
    if head not in event:
        return MISSING
    value = event[head]
    for segment in rest:
        if isinstance(value, dict):
            if segment not in value:
                return MISSING
            value = value[segment]
        elif isinstance(value, list) and segment.isascii() and segment.isdigit() and int(segment) < len(value):
            value = value[int(segment)]
        else:
            return MISSING
    return value


def template_resolver(event: EventView) -> Resolver:
    """Resolves template paths in `event`; a path whose first segment is not a root is read under `payload`.

    So `{{workflowId}}` is `{{payload.workflowId}}`, and a payload key named like a root needs the full path.
    """

    def resolve(path: tuple[str, ...]) -> JsonValue | Missing:
        return lookup(event, path if path[0] in event else ("payload", *path))

    return resolve


def compile_condition(condition: Condition) -> Predicate:
    """Build the predicate for `condition` once, so evaluation does no AST dispatch per event (SPEC §8)."""
    match condition:
        case And(args=args):
            return _all([compile_condition(arg) for arg in args])
        case Or(args=args):
            return _any([compile_condition(arg) for arg in args])
        case Not(arg=arg):
            return _not(compile_condition(arg))
        case Compare():
            return _compare(condition)
        case In():
            return _member(condition)
        case Contains():
            return _on_field(condition.field, lambda found: _contains(found, condition.value))
        case Glob():
            return _on_field(condition.field, lambda found: isinstance(found, str) and glob(condition.value, found))
        case Exists():
            path = condition.field.split(".")
            return lambda event: lookup(event, path) is not MISSING
        case _:
            assert_never(condition)


def fingerprint(rule_id: uuid.UUID, fields: Sequence[str], event: EventView) -> str:
    """Hex SHA-256 of the ASCII canonical JSON `[rule_id, value, …]`; a missing field counts as `null` (SPEC §9)."""
    return hashlib.sha256(canonical_fingerprint_input(rule_id, fields, event).encode("ascii")).hexdigest()


def canonical_fingerprint_input(rule_id: uuid.UUID, fields: Sequence[str], event: EventView) -> str:
    """The string `fingerprint` hashes: sorted keys, no whitespace, non-ASCII escaped as `\\uXXXX`."""
    values: list[JsonValue] = [str(rule_id)]
    for field in fields:
        found = lookup(event, field.split("."))
        values.append(None if found is MISSING else found)
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def glob(pattern: str, text: str) -> bool:
    """Whole-string match where `*` is any run of code points and `?` exactly one; case-sensitive, no `[...]`.

    Greedy two-pointer matching: O(len(pattern) * len(text)) at worst, with no backtracking blowup.
    """
    p = t = 0
    star = -1
    resume = 0
    while t < len(text):
        if p < len(pattern) and pattern[p] == "*":
            star, resume = p, t
            p += 1
        elif p < len(pattern) and pattern[p] in ("?", text[t]):
            p += 1
            t += 1
        elif star >= 0:
            resume += 1
            p, t = star + 1, resume
        else:
            return False
    while p < len(pattern) and pattern[p] == "*":
        p += 1
    return p == len(pattern)


def _all(parts: list[Predicate]) -> Predicate:
    return lambda event: all(part(event) for part in parts)


def _any(parts: list[Predicate]) -> Predicate:
    return lambda event: any(part(event) for part in parts)


def _not(inner: Predicate) -> Predicate:
    return lambda event: not inner(event)


def _on_field(field: str, test: Callable[[JsonValue], bool]) -> Predicate:
    """`test` on the field's value; `false` for a missing field (SPEC §8.1)."""
    path = field.split(".")

    def predicate(event: EventView) -> bool:
        found = lookup(event, path)
        return found is not MISSING and test(found)

    return predicate


def _compare(condition: Compare) -> Predicate:
    value = condition.value
    by_severity = condition.field == "severity"
    match condition.op:
        case "eq":
            return _on_field(condition.field, lambda found: _same(found, value))
        case "ne":
            return _on_field(condition.field, lambda found: _is_scalar(found) and not _same(found, value))
        case "gt" | "gte" | "lt" | "lte":
            op = condition.op
            return _on_field(condition.field, lambda found: _ordered(op, _order(found, value, by_severity)))
        case _:
            assert_never(condition.op)


def _member(condition: In) -> Predicate:
    values = condition.value
    match condition.op:
        case "in":
            return _on_field(condition.field, lambda found: any(_same(found, value) for value in values))
        case "not_in":
            return _on_field(
                condition.field,
                lambda found: _is_scalar(found) and not any(_same(found, value) for value in values),
            )
        case _:
            assert_never(condition.op)


def _contains(found: JsonValue, value: Scalar) -> bool:
    """Substring for a string field and a string value, membership for an array field, `false` otherwise."""
    if isinstance(found, str):
        return isinstance(value, str) and value in found
    if isinstance(found, list):
        return any(_same(item, value) for item in found)
    return False


def _is_scalar(value: JsonValue) -> bool:
    return not isinstance(value, (dict, list))


def _is_number(value: JsonValue) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _same(found: JsonValue, value: Scalar) -> bool:
    """JSON equality: `1 == 1.0`, but a bool is never a number and `1` never equals `"1"`."""
    if isinstance(found, bool) or isinstance(value, bool):
        return isinstance(found, bool) and isinstance(value, bool) and found == value
    if _is_number(found) and _is_number(value):
        return found == value
    if isinstance(found, str) and isinstance(value, str):
        return found == value
    return found is None and value is None


def _order(found: JsonValue, value: Scalar, by_severity: bool) -> int | None:
    """-1, 0 or 1 for two numbers, two strings or two severities; None for a type mismatch."""
    if by_severity:
        if not (isinstance(found, str) and isinstance(value, str)):
            return None
        found_rank, value_rank = _SEVERITY_RANK.get(found), _SEVERITY_RANK.get(value)
        if found_rank is None or value_rank is None:
            return None
        return (found_rank > value_rank) - (found_rank < value_rank)
    if _is_number(found) and _is_number(value):
        return (found > value) - (found < value)
    if isinstance(found, str) and isinstance(value, str):
        return (found > value) - (found < value)
    return None


def _ordered(op: Literal["gt", "gte", "lt", "lte"], order: int | None) -> bool:
    if order is None:
        return False
    match op:
        case "gt":
            return order > 0
        case "gte":
            return order >= 0
        case "lt":
            return order < 0
        case "lte":
            return order <= 0
        case _:
            assert_never(op)
