"""Structured YAML runbooks (SPEC §11.1): validated against `StructuredRunbook`; known guard phrases become
`StepGuard`s, the rest stay questions a human answers (SPEC §11.4).
"""

from dataclasses import dataclass

import yaml
from pydantic import ValidationError

from pagercutie.core.errors import FieldError, InvalidInput
from pagercutie.rules.ast import And, Compare, Condition
from pagercutie.runbooks.parsing.guards import parse_guard
from pagercutie.runbooks.schemas import StructuredRunbook
from pagercutie.runbooks.steps import Step, StepGuard

_ORIGINAL = "original"


@dataclass(frozen=True, kw_only=True)
class ParsedStructured:
    slug: str
    attach: Condition | None
    steps: list[Step]
    warnings: list[str]


def parse_structured(original: str) -> ParsedStructured:
    """Raises `InvalidInput` (422) when `original` is not YAML of the `StructuredRunbook` model."""
    try:
        runbook = StructuredRunbook.model_validate(_load_yaml(original))
    except ValidationError as e:
        raise InvalidInput([FieldError((_ORIGINAL, *error["loc"]), error["msg"]) for error in e.errors()]) from e
    steps: list[Step] = []
    warnings: list[str] = []
    for index, step in enumerate(runbook.steps):
        match step.if_:
            case StepGuard(step=target) if target >= index:
                raise InvalidInput([FieldError((_ORIGINAL, "steps", index, "if", "step"), "must be an earlier step")])
            case str(phrase):
                guard = parse_guard(phrase, steps)
                if guard is None:
                    warnings.append(f"Step {index + 1}: the guard {phrase!r} is not recognised; a human answers it")
                else:
                    step = step.model_copy(update={"if_": guard})
            case _:
                pass
        steps.append(step)
    return ParsedStructured(slug=runbook.runbook, attach=_attach(runbook), steps=steps, warnings=warnings)


def _load_yaml(original: str) -> object:
    """Safe YAML without aliases: an alias can expand a 100 kB document into gigabytes for validation."""
    try:
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(original, Loader=yaml.SafeLoader)):
            raise InvalidInput([FieldError((_ORIGINAL,), "YAML aliases (*name) are not supported")])
        return yaml.safe_load(original)
    except yaml.YAMLError as e:
        raise InvalidInput([FieldError((_ORIGINAL,), f"not valid YAML: {e}")]) from e


def _attach(runbook: StructuredRunbook) -> Condition | None:
    """`matches:` names payload fields (StructuredRunbook docstring); the condition addresses them under `payload.`."""
    if not runbook.matches:
        return None
    try:
        return And(
            op="and",
            args=[Compare(op="eq", field=f"payload.{field}", value=value) for field, value in runbook.matches.items()],
        )
    except ValidationError as e:
        raise InvalidInput([FieldError((_ORIGINAL, "matches"), error["msg"]) for error in e.errors()]) from e
