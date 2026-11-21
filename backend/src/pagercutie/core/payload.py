"""Reading values out of an event payload by `FieldPath`."""

from collections.abc import Mapping

from pydantic import JsonValue


def field_value(payload: Mapping[str, JsonValue], path: str) -> JsonValue:
    """The value at the dot path `path` (e.g. `error.code`); None when a step is missing or not an object."""
    current: JsonValue = dict(payload)
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
