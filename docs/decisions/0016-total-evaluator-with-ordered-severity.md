# ADR-0016: Total evaluator with ordered severity

- **ID:** ADR-0016
- **Timestamp:** 2026-11-20T21:00+01:00
- **Status:** Accepted
- **See:** SPEC §8.1

## Decision

The evaluator never raises: a missing field or type mismatch makes a predicate `false` (except `exists`). Severity is normalised at ingest to `debug < info < warn < error < critical`, so `gte warn` works. Field paths are rooted at `payload.`.

## Rationale

- Arbitrary user events must never crash evaluation.
- The brief's examples need "WARN or above" and use `{{payload.…}}` paths.
