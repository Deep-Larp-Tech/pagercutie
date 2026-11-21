"""Wiki / link runbooks (SPEC §11.1): one manual step, "open the runbook"."""

import re

from pagercutie.runbooks.parsing.text import MAX_STEP_TEXT, manual, parse_text
from pagercutie.runbooks.steps import Manual

_URL = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)
_PREFIX = "Open the runbook: "


def parse_link(original: str) -> tuple[list[Manual], list[str]]:
    """One "open the runbook" step; text that is not a single http(s) URL is shown as free text instead (RUN-8)."""
    url = original.strip()
    if _URL.match(url) and len(_PREFIX) + len(url) <= MAX_STEP_TEXT:
        return [manual(_PREFIX + url)], []
    steps, warnings = parse_text(original)
    return steps, ["The text is not a single http(s) URL; it is shown as free text", *warnings]
