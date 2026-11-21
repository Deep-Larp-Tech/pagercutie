# ADR-0014: OpenTelemetry with Grafana LGTM; measured end-to-end latency

- **ID:** ADR-0014
- **Timestamp:** 2026-11-20T20:56+01:00
- **Status:** Accepted, amended by ADR-0042 (traces cover the ingest request; no Kafka headers) and ADR-0061 (LGTM runs by default)
- **See:** SPEC §13

## Decision

All roles export OpenTelemetry to `grafana/otel-lgtm`. Ingest stamps `received_at_ms`; the dispatcher records `end_to_end_latency_seconds`, from which Grafana shows p50/p99. Traces propagate through Kafka headers.

## Rationale

- The brief requires measured, not estimated, throughput and latency (`NFR-3`).
- The scaffold already ships the OTel setup; a committed dashboard doubles as demo material.
