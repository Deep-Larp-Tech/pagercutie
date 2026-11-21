"""Free-text runbooks (SPEC §11.1): the whole text becomes manual steps, one unless it is too long for a step."""

import re

from pagercutie.runbooks.steps import Manual

MAX_STEP_TEXT = 2000

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def parse_text(original: str) -> tuple[list[Manual], list[str]]:
    """Manual steps showing `original`, and warnings. Callers reject blank text first."""
    chunks = chunk(original.strip())
    warnings = (
        []
        if len(chunks) == 1
        else [f"The text is longer than {MAX_STEP_TEXT} characters; split it into {len(chunks)} manual steps"]
    )
    return [manual(part) for part in chunks], warnings


def manual(text: str) -> Manual:
    return Manual(action="manual", text=text)


def chunk(text: str) -> list[str]:
    """`text` split into pieces of at most MAX_STEP_TEXT characters, at paragraph breaks, then whitespace."""
    pieces: list[str] = []
    current = ""
    for paragraph in _PARAGRAPH_BREAK.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= MAX_STEP_TEXT:
            current = candidate
            continue
        if current:
            pieces.append(current)
        while len(paragraph) > MAX_STEP_TEXT:
            cut = paragraph.rfind(" ", 0, MAX_STEP_TEXT + 1)
            cut = cut if cut > 0 else MAX_STEP_TEXT
            pieces.append(paragraph[:cut].rstrip())
            paragraph = paragraph[cut:].lstrip()
        current = paragraph
    if current:
        pieces.append(current)
    return pieces
