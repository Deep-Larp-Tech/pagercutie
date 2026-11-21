"""`{{field}}` template rendering for event payloads and delivery messages."""

import json
import re
from collections.abc import Mapping
from typing import assert_never

from pydantic import JsonValue

from pagercutie.core.enums import Channel
from pagercutie.core.payload import field_value

SMS_MAX_LENGTH = 160
"""Characters of a single SMS segment; SMS and phone messages are cut to this length."""

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
_PAYLOAD_ROOT = "payload."


def render(template: str, payload: Mapping[str, JsonValue]) -> str:
    """Replace each `{{path}}` or `{{payload.path}}` with the payload value (a missing field renders as `""`)."""

    def replace(match: re.Match[str]) -> str:
        path = match.group(1).removeprefix(_PAYLOAD_ROOT)
        return _text(field_value(payload, path))

    return _PLACEHOLDER.sub(replace, template)


def render_message(channel: Channel, title: str, body: str | None) -> str:
    """The text stored on a delivery for `channel`, built from an already rendered title and body."""
    match channel:
        case Channel.SMS | Channel.PHONE:
            return title[:SMS_MAX_LENGTH]
        case Channel.EMAIL:
            return f"{title}\n\n{body}" if body else title
        case Channel.UI:
            return f"{title}\n{body}" if body else title
        case _:
            assert_never(channel)


def _text(value: JsonValue) -> str:
    """Strings as-is, null as empty, every other JSON value as compact JSON."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
