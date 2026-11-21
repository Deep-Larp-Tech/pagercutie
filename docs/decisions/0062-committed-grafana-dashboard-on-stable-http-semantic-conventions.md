# ADR-0062: Committed Grafana dashboard on stable HTTP semantic conventions

- **ID:** ADR-0062
- **Timestamp:** 2026-11-21T04:00+01:00
- **Status:** Accepted
- **See:** SPEC §13, ADR-0061, `observability/grafana/`

## Decision

- `observability/grafana/dashboards/pagercutie.json` is provisioned into `otel-lgtm` through a file provider
  (`observability/grafana/dashboards.yaml`) and set as Grafana's home dashboard. Rows: pipeline (SPEC §13 metric
  names), backend, Postgres, logs and traces. A `Replica` variable filters by `service_instance_id`.
- The backend runs with `OTEL_SEMCONV_STABILITY_OPT_IN=http` (compose and `mise run dev`), so HTTP metrics are
  `http_server_request_duration_seconds` with `http_route` and `http_response_status_code`.
- The backend exports metrics every 10 s instead of the SDK's 60 s: Grafana's `$__rate_interval` assumes a 15 s
  scrape, and `rate()` over a 60 s push left the HTTP panels empty.
- Postgres panels use Tempo's span metrics from the SQLAlchemy spans instead of a Postgres exporter.
- `SQLAlchemyInstrumentor` runs with `skip_dep_check=True`: 0.66b2 declares `sqlalchemy < 2.1` and instrumented
  nothing on 2.1.9, while upstream main already allows `< 2.2`. Remove the flag once a release includes that.

| Option | Tradeoff |
|---|---|
| **Stable HTTP conventions** (chosen) | Names stay put when the instrumentation's default flips. Span attributes change too (`http.request.method`, `url.path`). |
| Old conventions (default today) | No setting; the dashboard breaks on the upgrade that drops `http_server_duration_milliseconds` and `http_target`. |
| Image's bundled RED dashboard | Already in `otel-lgtm`; shows no replicas, Postgres, pipeline metrics or logs. |

## Rationale

- SPEC §13 calls for a committed dashboard for the load-test demo, where scaling the backend must be visible per
  replica.
- Pipeline panels query the SPEC §13 names now, so a stage shows up as soon as it records its metric.
- Span metrics give SQL rate and latency with no extra container.
