"""Markdown runbooks (SPEC §11.1): numbered, bulleted and checklist items become manual steps.

Links stay in the step text for the UI to render. A link outside the list (`See [the dashboard](https://…)`) becomes
its own "Open …" step in document order, so it is not lost. Headings and other prose stay in the original only.
"""

import re

from pagercutie.runbooks.parsing.text import chunk, manual, parse_text
from pagercutie.runbooks.steps import Manual

_ITEM = re.compile(r"^(?P<indent>\s*)(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(?P<text>\S.*)$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}(?:\s|$)")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_LINK = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)|(?P<bare><?https?://[^\s<>)]+>?)")


def parse_markdown(original: str) -> tuple[list[Manual], list[str]]:
    """Manual steps from the list items and prose links of `original`, and warnings."""
    items: list[str] = []
    in_item = False
    in_fence = False
    skipped_prose = False
    for line in original.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            in_item = False
            skipped_prose = True
            continue
        if in_fence:
            continue
        if item := _ITEM.match(line):
            items.append(item["text"].strip())
            in_item = True
        elif not line.strip():
            in_item = False
        elif in_item and line[:1].isspace():
            items[-1] = f"{items[-1]} {line.strip()}"
        elif _HEADING.match(line):
            in_item = False
        else:
            in_item = False
            links = [_open_step(link) for link in _LINK.finditer(line)]
            items.extend(links)
            skipped_prose = skipped_prose or not links or bool(_LINK.sub("", line).strip(" .,:;-"))
    if not items:
        steps, warnings = parse_text(original)
        return steps, ["No list items found; the text is shown as free text", *warnings]
    warnings = ["Text outside list items is shown only in the original"] if skipped_prose else []
    steps: list[Manual] = []
    for text in items:
        parts = chunk(text)
        if len(parts) > 1:
            warnings.append(f"An item longer than 2000 characters was split into {len(parts)} manual steps")
        steps.extend(manual(part) for part in parts)
    return steps, warnings


def _open_step(link: re.Match[str]) -> str:
    if link["bare"]:
        return f"Open {link['bare'].strip('<>')}"
    return f"Open [{link['title']}]({link['url']})"
