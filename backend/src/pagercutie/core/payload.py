"""Reading values out of an event payload by `FieldPath` (SPEC §4.3)."""

from collections.abc import Mapping

from pydantic import JsonValue

from pagercutie.core.fields import MISSING, lookup


def field_value(payload: Mapping[str, JsonValue], path: str) -> JsonValue:
    """The value at the dot path `path` (e.g. `error.code`, `items.0.sku`); None when the path leads nowhere."""
    found = lookup(payload, path.split("."))
    return None if found is MISSING else found
