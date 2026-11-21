"""The action a step's `run()` returns, what it receives and what it produces (SPEC §11.2, ADR-0039)."""

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


class ActionContext:
    """Integrations a step's `run()` uses to build its action (HTTP client, mock service, escalation). Members are
    added with the first concrete action; the executor builds one and passes it to `RunbookRun`."""
