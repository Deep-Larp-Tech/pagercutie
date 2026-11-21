"""Text templates with `{{ path }}` placeholders, parsed once and rendered per event (SPEC §11.2), and the
per-channel delivery message (SPEC §10).

Only direct replacement for now. Anything else between `{{` and `}}` is a syntax error, so adding filters or
functions later cannot change what an existing template renders. `contract/template-tests.json` pins the behaviour
for every implementation.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import assert_never

from pydantic import JsonValue

from pagercutie.core.enums import Channel
from pagercutie.core.fields import FIELD_PATH_PATTERN, Missing

_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_PATH = re.compile(FIELD_PATH_PATTERN)

SMS_MAX_LENGTH = 160
"""Characters of a single SMS segment; SMS and phone messages are cut to this length."""


@dataclass(frozen=True)
class Text:
    """Literal text between placeholders."""

    value: str


@dataclass(frozen=True)
class Placeholder:
    """`{{ path }}`, replaced by the value at the split field path."""

    path: tuple[str, ...]


type Node = Text | Placeholder


@dataclass(frozen=True)
class CompiledTemplate:
    """A parsed template: its nodes in source order."""

    nodes: tuple[Node, ...]


type Resolver = Callable[[tuple[str, ...]], JsonValue | Missing]


class TemplateSyntaxError(ValueError):
    """The text is not a valid template."""


def parse(text: str) -> CompiledTemplate:
    """Raises `TemplateSyntaxError` for an unclosed `{{` or a placeholder that is not a field path."""
    nodes: list[Node] = []
    position = 0
    for found in _PLACEHOLDER.finditer(text):
        expression = found.group(1).strip()
        if not _PATH.fullmatch(expression):
            raise TemplateSyntaxError(f"placeholder at offset {found.start()} is not a field path: {found.group()!r}")
        if found.start() > position:
            nodes.append(Text(text[position : found.start()]))
        nodes.append(Placeholder(tuple(expression.split("."))))
        position = found.end()
    rest = text[position:]
    if "{{" in rest:
        raise TemplateSyntaxError(f"unclosed '{{{{' at offset {position + rest.index('{{')}")
    if rest:
        nodes.append(Text(rest))
    return CompiledTemplate(tuple(nodes))


def render(template: CompiledTemplate, resolve: Resolver) -> str:
    """Total: never raises, whatever `resolve` returns."""
    return "".join(_render(node, resolve) for node in template.nodes)


def format_value(value: JsonValue | Missing) -> str:
    """Strings as they are; null and missing as empty; numbers, booleans, arrays and objects as compact JSON."""
    match value:
        case Missing() | None:
            return ""
        case str():
            return value
        case _:
            return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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


def _render(node: Node, resolve: Resolver) -> str:
    match node:
        case Text(value=value):
            return value
        case Placeholder(path=path):
            return format_value(resolve(path))
        case _:
            assert_never(node)
