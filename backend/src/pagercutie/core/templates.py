"""Text templates with `{{ path }}` placeholders, parsed once and rendered per event (SPEC §11.2).

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

from pagercutie.core.fields import FIELD_PATH_PATTERN, Missing

_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_PATH = re.compile(FIELD_PATH_PATTERN)


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


# The value at a split field path, or `MISSING`.
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


def _render(node: Node, resolve: Resolver) -> str:
    match node:
        case Text(value=value):
            return value
        case Placeholder(path=path):
            return format_value(resolve(path))
        case _:
            assert_never(node)
