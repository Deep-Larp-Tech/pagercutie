# ADR-0115: Request logging is a pure ASGI middleware; FastAPI drops its receive/send spans

- **ID:** ADR-0115
- **Timestamp:** 2026-11-22T10:00+01:00
- **Status:** Accepted
- **See:** SPEC §13, `backend/src/pagercutie/core/log.py`, `backend/src/pagercutie/core/telemetry.py`

## Context

Under `mise run demo:load` one backend replica (one uvicorn process, one event loop) was CPU-bound at about
360 events/s with OpenTelemetry on and 640 events/s with it off, while Postgres sat at 15-25% CPU. A saturated loop
delays every await: UI delivery latency was p50 690 ms / p99 2.4 s under load against 31 ms idle. Work done for
every request, whatever its payload, adds directly to that latency.

## Decision

- `RequestLoggingMiddleware` (`core/log.py`) is a pure ASGI middleware, registered with `app.add_middleware`,
  instead of `app.middleware("http")`, whose `BaseHTTPMiddleware` adds a task group and response wrapping per
  request. Behaviour is unchanged: request ID from `x-request-id` or a new one, bound in the structlog context, one
  `http.request` line when the response starts, `x-request-id` echoed. WebSocket and lifespan scopes pass through.
- `FastAPIInstrumentor.instrument_app` gets `exclude_spans=["receive", "send"]`, dropping the internal
  `http receive` / `http send` spans of every request. Sampling and the SQLAlchemy and Redis spans are unchanged.

## Options

| Option | Tradeoff |
|---|---|
| **Pure ASGI middleware, fewer HTTP spans** (chosen) | Same logs and traces minus two internal spans; a little more code than a decorator. |
| Keep `BaseHTTPMiddleware` | Simplest code; a task group and wrapped response on every ingest request. |
| Sample traces | Less CPU, but the slow-trace panel and per-delivery trace links lose data. |

## Rationale

- The `receive`/`send` spans carry no information the server span lacks.
- The middleware rewrite removes per-request overhead without changing any log field (`path` is now the raw
  `scope["path"]`, which differs only for paths containing `?`, `#` or `\`).
