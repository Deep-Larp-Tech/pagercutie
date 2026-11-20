# ADR-0017: Fingerprint dedup also implements grouping

- **ID:** ADR-0017
- **Timestamp:** 2026-11-20T21:02+01:00
- **Status:** Accepted
- **See:** SPEC §9

## Decision

Fingerprint = `sha256(rule_id + values of rule.dedup.fields)` within `window_s`. Grouping ("one alert per instrument every 5 minutes") is the same mechanism. A unique index on open alerts' fingerprints makes the upsert idempotent.

## Rationale

- One concept covers both `NOI-1` and the brief's grouping example.
- 500 identical errors cost about two Postgres writes.
