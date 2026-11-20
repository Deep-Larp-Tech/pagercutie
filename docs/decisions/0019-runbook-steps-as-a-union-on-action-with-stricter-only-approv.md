# ADR-0019: Runbook steps as a union on `action` with stricter-only approvals

- **ID:** ADR-0019
- **Timestamp:** 2026-11-20T21:06+01:00
- **Status:** Accepted
- **See:** SPEC §11.2, §11.3

## Decision

Steps are Pydantic models tagged by `action`, the key the brief's YAML uses. Each action has a default approval; a runbook may only make it stricter. Steps run in an executor role from a Postgres job table, as a per-alert state machine.

## Rationale

- Adding an action is one model plus one handler, guarded by the same merge checks as conditions.
- Safety rule easy to explain: risky actions can never be made approval-free (`RUN-4`).
- Actions are low-volume, so they need no topic.
