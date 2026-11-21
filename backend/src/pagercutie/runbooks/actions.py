"""The abstract action a runbook step is turned into (SPEC §11.2). Built by `factory.StepFactory`."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import JsonValue


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    summary: str  # shown on the alert, e.g. "HTTP 200 in 35 ms"
    outputs: Mapping[str, JsonValue] = field(default_factory=dict)


class Action(ABC):
    @abstractmethod
    async def run(self) -> ActionResult:
        """Perform the action. Expected failures are a result with `ok=False`, not an exception."""
