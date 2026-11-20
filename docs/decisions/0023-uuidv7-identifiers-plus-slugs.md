# ADR-0023: UUIDv7 identifiers plus slugs

- **ID:** ADR-0023
- **Timestamp:** 2026-11-20T21:22+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §1

## Decision

All entities have backend-generated UUIDv7 IDs. Entities people refer to by name (teams, sources, event schemas, runbooks) also have a unique slug.

## Rationale

- Matches the scaffold; time-ordered IDs index well.
- Hand-written runbook YAML refers to slugs (`runbook: settlement-timeout`, `team: counterparty-support`).
