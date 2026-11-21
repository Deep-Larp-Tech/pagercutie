"""Turns runbook text into steps and guards by matching words (SPEC §11.1, §11.4, ADR-0037).

A text item becomes the step built by the first step rule that matches it, otherwise a `manual` step. Guard text
(`if:`) becomes the `StepGuard` built by the first guard rule that matches, otherwise it stays text that a human
answers yes / no. Interpreted steps keep the action's default approval (`factory.requires_approval`, RUN-4), so a
matched `restart_service` or `escalate` still waits for approval.
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import ClassVar

from pagercutie.runbooks.steps import Manual, Step, StepGuard

_TRAILING_PUNCTUATION = ".?!:;"
_COUNT_WORDS = {"once": 1, "twice": 2, "thrice": 3}


class PhraseRule[T](ABC):
    """Builds a `T` from text that matches `phrase` as a whole, ignoring case and surrounding whitespace."""

    phrase: ClassVar[str]
    """Regular expression for the whole text; named groups carry the values `build` needs."""

    def match(self, text: str, earlier: Sequence[Step]) -> T | None:
        """The value for `text`, or None when the phrase does not match or `build` rejects it."""
        found = re.fullmatch(self.phrase, _normalise(text), re.IGNORECASE)
        return None if found is None else self.build(found, earlier)

    @abstractmethod
    def build(self, found: re.Match[str], earlier: Sequence[Step]) -> T | None:
        """The value for a matched phrase, or None to let later rules try. `earlier` are the steps before this one."""


type StepRule = PhraseRule[Step]
type GuardRule = PhraseRule[StepGuard]


class StepInterpreter(ABC):
    """Applies ordered word rules to runbook text. Concrete interpreters choose the rules; the first match wins."""

    @property
    @abstractmethod
    def step_rules(self) -> Sequence[StepRule]:
        """Rules that turn a checklist item into an executable step, tried in order."""

    @property
    @abstractmethod
    def guard_rules(self) -> Sequence[GuardRule]:
        """Rules that turn `if:` text into a structured guard, tried in order."""

    def interpret_step(self, text: str, earlier: Sequence[Step] = ()) -> Step:
        """The step for one checklist item; a `manual` step showing the text when no rule matches."""
        step = _first_match(self.step_rules, text, earlier)
        return Manual(action="manual", text=text) if step is None else step

    def interpret_steps(self, texts: Iterable[str]) -> list[Step]:
        """Steps for checklist items in order; each item sees the steps interpreted before it."""
        steps: list[Step] = []
        for text in texts:
            steps.append(self.interpret_step(text, steps))
        return steps

    def interpret_guard(self, text: str, earlier: Sequence[Step]) -> StepGuard | str:
        """The structured guard for `if:` text, or the text itself, which becomes a yes / no question (SPEC §11.4)."""
        guard = _first_match(self.guard_rules, text, earlier)
        return text if guard is None else guard

    def resolve_guards(self, steps: Sequence[Step]) -> list[Step]:
        """`steps` with every text guard that a guard rule matches replaced by its `StepGuard`."""
        resolved: list[Step] = []
        for step in steps:
            if isinstance(step.if_, str):
                guard = self.interpret_guard(step.if_, resolved)
                if isinstance(guard, StepGuard):
                    step = step.model_copy(update={"if_": guard})
            resolved.append(step)
        return resolved


class FailuresGuardRule(PhraseRule[StepGuard]):
    """`[if] <step> fails once | twice | thrice | N times` (SPEC §11.4).

    `<step>` names an earlier step by its action, in full (`retry_workflow`, `retry workflow`) or by its first word
    (`retry`). The latest such step is meant, so "retry fails twice" after two retries guards on the second one.
    """

    phrase = r"(?:if )?(?P<subject>[a-z][a-z_ ]*?) (?:fails?|failed) (?P<count>once|twice|thrice|\d+ times?)"

    def build(self, found: re.Match[str], earlier: Sequence[Step]) -> StepGuard | None:
        subject = found["subject"].lower().replace("_", " ")
        count = _parse_count(found["count"].lower())
        if count < 1:
            return None
        for index in reversed(range(len(earlier))):
            action = earlier[index].action.replace("_", " ")
            if subject in (action, action.split(" ", 1)[0]):
                return StepGuard(step=index, failures_gte=count)
        return None


def _first_match[T](rules: Sequence[PhraseRule[T]], text: str, earlier: Sequence[Step]) -> T | None:
    for rule in rules:
        value = rule.match(text, earlier)
        if value is not None:
            return value
    return None


def _normalise(text: str) -> str:
    return " ".join(text.split()).rstrip(_TRAILING_PUNCTUATION).rstrip()


def _parse_count(count: str) -> int:
    word = _COUNT_WORDS.get(count)
    return int(count.split(" ", 1)[0]) if word is None else word
