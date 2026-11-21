"""Integrations the runbook steps act through, injected into `run_step` (SPEC §11.2).

Each integration is a Protocol, so replacing a simulation touches only its implementation (ADR-0013).
"""

import time
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
from pydantic import JsonValue

from pagercutie.pipeline.executor.outcomes import StepFailed, StepSucceeded

HTTP_TIMEOUT_SECONDS = 5.0


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

    async def request(self, method: Literal["GET", "POST", "PUT"], url: str, json: JsonValue | None) -> HttpResult:
        """Send the request with `json` as the body when it is not None.

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

    async def request(self, method: Literal["GET", "POST", "PUT"], url: str, json: JsonValue | None) -> HttpResult:
        started = time.perf_counter()
        try:
            response = await self._client.request(method, url, json=json)
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise HttpError(str(error) or type(error).__name__) from error
        return HttpResult(
            status=response.status_code,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )


class OpsService(Protocol):
    """The operations backend for `retry_workflow`, `restart_service` and `open_ticket`."""

    async def retry_workflow(self, workflow_id: str) -> StepSucceeded | StepFailed: ...

    async def restart_service(self, service: str) -> StepSucceeded | StepFailed: ...

    async def open_ticket(self, title: str) -> StepSucceeded | StepFailed: ...


class SimulatedOps:
    """Accepts every operation in-process. SPEC §11.2's mock service replaces it later (ADR-0013)."""

    async def retry_workflow(self, workflow_id: str) -> StepSucceeded | StepFailed:
        return StepSucceeded(f"Simulated: retry of workflow {workflow_id} accepted")

    async def restart_service(self, service: str) -> StepSucceeded | StepFailed:
        return StepSucceeded(f"Simulated: restart of service {service} accepted")

    async def open_ticket(self, title: str) -> StepSucceeded | StepFailed:
        return StepSucceeded(f"Simulated: ticket '{title}' opened")


@dataclass(frozen=True)
class Integrations:
    """What `run_step` acts through."""

    http: HttpClient
    ops: OpsService
