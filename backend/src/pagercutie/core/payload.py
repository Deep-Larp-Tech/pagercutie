"""Reading values out of an event or its payload by `FieldPath` (SPEC §4.3, ADR-0060)."""

from collections.abc import Mapping, Sequence
from enum import Enum

from pydantic import JsonValue


class Missing(Enum):
    """Marks a field path that leads nowhere; distinct from a JSON `null`."""

    MISSING = "missing"


MISSING = Missing.MISSING


def lookup(root: Mapping[str, JsonValue], path: Sequence[str]) -> JsonValue | Missing:
    """The value at the split field path, or `MISSING`. ASCII-digit segments index into arrays."""
    head, *rest = path
    if head not in root:
        return MISSING
    value = root[head]
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


def field_value(payload: Mapping[str, JsonValue], path: str) -> JsonValue:
    """The value at the dot path `path` (e.g. `error.code`, `items.0.sku`); None when the path leads nowhere."""
    found = lookup(payload, path.split("."))
    return None if found is MISSING else found
