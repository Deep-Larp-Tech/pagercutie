# ADR-0010: Raw events stay in the broker; invalid events go to a dead-letter topic

- **ID:** ADR-0010
- **Timestamp:** 2026-11-20T20:48+01:00
- **Status:** Superseded by ADR-0042 (invalid events are answered with 422; raw events are not kept)
- **See:** SPEC §7

## Decision

Ingest does not store events in Postgres; the `events` topic with time-based retention is the raw log. Events failing schema resolution or validation go to `events-dlq`.

## Rationale

- Keeps Postgres off the high-volume path.
- Nothing is silently dropped, and rejections are counted in metrics.
