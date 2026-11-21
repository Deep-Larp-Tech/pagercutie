"""Integrations the runbook steps act through, injected into `perform.run_action` (SPEC §11.2).

Each integration is a Protocol, so replacing a simulation touches only its implementation (ADR-0013). Every call takes
the attempt's idempotency key: a repeated attempt after a lost replica sends the same key, so an integration that
honours it acts once (ADR-0106).
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal, Protocol

import httpx
from pydantic import JsonValue

from pagercutie.pipeline.executor.outcomes import StepFailed, StepSucceeded

HTTP_TIMEOUT_SECONDS = 5.0
IDEMPOTENCY_HEADER = "Idempotency-Key"


class HttpError(Exception):
    """The request did not complete (timeout, connection refused, invalid URL). The message is the short reason."""


@dataclass(frozen=True)
class HttpResult:
    """A completed HTTP exchange, whatever its status."""

    status: int
    # Wall-clock time from sending the request to receiving the response headers.
    elapsed_ms: int


class HttpClient(Protocol):
    """Calls URLs for `http_get` and `call_webhook`."""

    async def request(
        self, method: Literal["GET", "POST", "PUT"], url: str, json: JsonValue | None, idempotency_key: uuid.UUID
    ) -> HttpResult:
        """Send the request with `json` as the body when it is not None and the key in the `Idempotency-Key` header.

        A non-2xx status is a normal result. Raises `HttpError` when no response arrived.
        """
        ...


def create_http_client() -> httpx.AsyncClient:
    """The shared client behind `HttpxClient`; the caller closes it."""
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)


class HttpxClient:
    """`HttpClient` over a shared `httpx.AsyncClient`."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def request(
        self, method: Literal["GET", "POST", "PUT"], url: str, json: JsonValue | None, idempotency_key: uuid.UUID
    ) -> HttpResult:
        started = time.perf_counter()
        try:
            response = await self._client.request(
                method, url, json=json, headers={IDEMPOTENCY_HEADER: str(idempotency_key)}
            )
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise HttpError(str(error) or type(error).__name__) from error
        return HttpResult(
            status=response.status_code,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )


class OpsService(Protocol):
    """The operations backend for `retry_workflow`, `restart_service` and `open_ticket`.

    A call with a key it has seen returns the first call's result without acting again.
    """

    async def retry_workflow(self, workflow_id: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed: ...

    async def restart_service(self, service: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed: ...

    async def open_ticket(self, title: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed: ...


@dataclass
class SimulatedOps:
    """Accepts every operation in-process. SPEC §11.2's mock service replaces it later (ADR-0013).

    Remembers the result of each idempotency key for the life of the replica and answers a repeated key from memory;
    other replicas do not see these keys (ADR-0106).
    """

    # The operations this replica performed, oldest first; a repeated key adds nothing.
    performed: list[str] = field(default_factory=list)
    _results: dict[uuid.UUID, StepSucceeded | StepFailed] = field(default_factory=dict)

    async def retry_workflow(self, workflow_id: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed:
        return self._once(idempotency_key, f"Simulated: retry of workflow {workflow_id} accepted")

    async def restart_service(self, service: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed:
        return self._once(idempotency_key, f"Simulated: restart of service {service} accepted")

    async def open_ticket(self, title: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed:
        return self._once(idempotency_key, f"Simulated: ticket '{title}' opened")

    def _once(self, key: uuid.UUID, result: str) -> StepSucceeded | StepFailed:
        known = self._results.get(key)
        if known is not None:
            return known
        self.performed.append(result)
        outcome = StepSucceeded(result)
        self._results[key] = outcome
        return outcome


@dataclass(frozen=True)
class Integrations:
    """What `perform.run_action` acts through."""

    http: HttpClient
    ops: OpsService
