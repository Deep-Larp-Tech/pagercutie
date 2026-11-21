"""Step guard phrases (SPEC §11.4, ADR-0020): `<step> fails (once|twice|thrice|N times)` → `StepGuard`.

`<step>` is `step N` (1-based) or a word naming an action (`retry`, `restart`, `webhook`, ...); a word resolves to the
nearest earlier step with that action. Anything else is not recognised and stays free text that a human answers.
"""

import re
from collections.abc import Sequence
from typing import assert_never

from pagercutie.runbooks.steps import (
    CallWebhook,
    Escalate,
    HttpGet,
    Manual,
    OpenTicket,
    RestartService,
    RetryWorkflow,
    Step,
    StepGuard,
    Wait,
)

_GUARD = re.compile(
    r"^(?:if\s+)?(?:the\s+)?(?P<subject>.+?)\s+(?:fails|has\s+failed|failed)\s+(?:at\s+least\s+)?"
    r"(?P<count>once|twice|thrice|(?P<n>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+times?)\s*[.!?]?$",
    re.IGNORECASE,
)
_STEP_NUMBER = re.compile(r"^step\s+#?(?P<number>\d+)$")
_COUNT_WORDS = {
    "once": 1,
    "twice": 2,
    "thrice": 3,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
# StepGuard has no upper bound; this keeps a typo like "fails 99999999999999999999 times" from parsing.
_MAX_FAILURES = 1000


def parse_guard(text: str, earlier: Sequence[Step]) -> StepGuard | None:
    """The structured guard for `text` on the step after `earlier`, or None when the phrase is not recognised."""
    match = _GUARD.match(" ".join(text.split()))
    if match is None:
        return None
    count = match["n"] or match["count"]
    failures = int(count) if count.isdigit() else _COUNT_WORDS[count.lower()]
    if not 1 <= failures <= _MAX_FAILURES:
        return None
    index = _resolve_step(_normalise(match["subject"]), earlier)
    return None if index is None else StepGuard(step=index, failures_gte=failures)


def _resolve_step(subject: str, earlier: Sequence[Step]) -> int | None:
    if number := _STEP_NUMBER.match(subject):
        index = int(number["number"]) - 1
        return index if 0 <= index < len(earlier) else None
    for index in range(len(earlier) - 1, -1, -1):
        if subject in _names(earlier[index]):
            return index
    return None


def _normalise(words: str) -> str:
    return " ".join(words.lower().replace("_", " ").replace("-", " ").split())


def _names(step: Step) -> frozenset[str]:
    """Words a guard may use for a step of this action, normalised (lowercase, `_` and `-` as spaces)."""
    match step:
        case HttpGet():
            return frozenset({"http get", "health check", "check", "request"})
        case RetryWorkflow():
            return frozenset({"retry workflow", "retry", "workflow retry"})
        case RestartService():
            return frozenset({"restart service", "restart", "service restart"})
        case CallWebhook():
            return frozenset({"call webhook", "webhook", "webhook call"})
        case OpenTicket():
            return frozenset({"open ticket", "ticket"})
        case Escalate():
            return frozenset({"escalate", "escalation"})
        case Wait():
            return frozenset({"wait"})
        case Manual():
            return frozenset({"manual", "manual step"})
        case _:
            assert_never(step)
