"""Runbook parsing (SPEC §11.1, ADR-0018): pure functions from (format, original text) to steps.

Shared by `POST /runbooks/parse` and runbook create and update, so the preview always matches what is saved.
"""

from dataclasses import dataclass
from typing import assert_never

from pagercutie.core.errors import FieldError, InvalidInput
from pagercutie.rules.ast import Condition
from pagercutie.runbooks.parsing.link import parse_link
from pagercutie.runbooks.parsing.markdown import parse_markdown
from pagercutie.runbooks.parsing.structured import parse_structured
from pagercutie.runbooks.parsing.text import parse_text
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import Step


@dataclass(frozen=True, kw_only=True)
class ParsedRunbook:
    slug: str | None = None
    """The `runbook:` slug of a structured runbook; None for the other formats."""
    attach: Condition | None = None
    """From a structured runbook's `matches:`; None for the other formats."""
    steps: list[Step]
    warnings: list[str]
    """Parts that fell back to manual steps or human-answered guards."""


def parse_runbook(format: RunbookFormat, original: str) -> ParsedRunbook:
    """Raises `InvalidInput` (422) for blank text and for a structured runbook that does not validate."""
    if not original.strip():
        raise InvalidInput([FieldError(("original",), "must not be blank")])
    match format:
        case RunbookFormat.STRUCTURED:
            parsed = parse_structured(original)
            return ParsedRunbook(slug=parsed.slug, attach=parsed.attach, steps=parsed.steps, warnings=parsed.warnings)
        case RunbookFormat.MARKDOWN:
            steps, warnings = parse_markdown(original)
        case RunbookFormat.TEXT:
            steps, warnings = parse_text(original)
        case RunbookFormat.LINK:
            steps, warnings = parse_link(original)
        case _:
            assert_never(format)
    return ParsedRunbook(steps=list(steps), warnings=warnings)
