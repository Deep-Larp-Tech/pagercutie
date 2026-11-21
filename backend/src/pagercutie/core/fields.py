"""Field paths into the normalised event, shared by rule conditions, the fingerprint and templates (SPEC §4.3)."""

from collections.abc import Mapping, Sequence
from enum import Enum

from pydantic import JsonValue

FIELD_PATH_PATTERN = r"[A-Za-z_]\w*(\.\w+)*"


class Missing(Enum):
    """Marks a field path that leads nowhere; distinct from a JSON `null`."""

    MISSING = "missing"


MISSING = Missing.MISSING


def lookup(root: Mapping[str, JsonValue], path: Sequence[str]) -> JsonValue | Missing:
    """The value at the split field path, or `MISSING`. ASCII-digit segments index into arrays (ADR-0060)."""
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
