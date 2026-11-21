# ADR-0046: Grafana LGTM in the default compose stack

- **ID:** ADR-0046
- **Timestamp:** 2026-11-21T03:30+01:00
- **Status:** Accepted
- **See:** SPEC §13, ADR-0014, `compose.yaml`, `backend/src/pagercutie/core/telemetry.py`

## Decision

- `otel-lgtm` (`grafana/otel-lgtm:0.41.1`) runs in the default `docker compose up`, with no profile. Its data lives
  in the `lgtm-data` volume, and its ports move with `GRAFANA_PORT`, `OTLP_GRPC_PORT` and `OTLP_HTTP_PORT`.
- The compose `backend` exports by default (`APP_OTEL_ENABLED=true`) and waits for `otel-lgtm` to be healthy.
- `mise run up` starts `otel-lgtm` too, and `mise run dev` sets `APP_OTEL_ENABLED=true`. The Python default stays
  `false`, so tests do not export.
- The backend exports metrics over OTLP as well as traces and logs. The FastAPI and SQLAlchemy instrumentations
  record HTTP and database metrics through the same `MeterProvider`.

| Option | Tradeoff |
|---|---|
| **Default service** (chosen) | Grafana is up for every demo and load test with no extra flag. One 885 MB pull (3.6 GB on disk); healthy about 7 s after start once pulled. |
| `observability` profile (previous) | Lighter stack. Needs both `--profile observability` and `APP_OTEL_ENABLED=true` before anything reaches Grafana. |

## Rationale

- `NFR-3` asks for measured latency and throughput, and the demo shows Grafana live while replicas scale (SPEC §13).
- Waiting for `service_healthy` keeps the traces of the first requests, which a `service_started` dependency
  drops while the collector boots.
- The tag is pinned so a new LGTM release cannot change the stack during the hackathon.
