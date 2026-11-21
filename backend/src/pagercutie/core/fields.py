"""Field paths into the normalised event, shared by rule conditions, the fingerprint and templates (SPEC §4.3)."""

from enum import Enum

# Dot path, e.g. `payload.error.code`; an all-digit segment indexes into an array.
FIELD_PATH_PATTERN = r"[A-Za-z_]\w*(\.\w+)*"


class Missing(Enum):
    """Marks a field path that leads nowhere; distinct from a JSON `null`."""

    MISSING = "missing"


MISSING = Missing.MISSING
