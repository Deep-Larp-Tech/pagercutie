# ADR-0029: Remove the scaffold example domain

- **ID:** ADR-0029
- **Timestamp:** 2026-11-20T21:45+01:00
- **Status:** Accepted
- **See:** README.md

## Decision

The scaffold's LARP example (persons, skills, LARP events, imports), its tests, factories and its initial
migration are deleted. The migration history starts empty; local databases created with the old migration must be
reset (`docker compose down -v`).

## Rationale

- Its endpoints and types polluted the contract and the generated frontend client.
- The scaffold's structure (router → service → models, DTO rules, test setup) stays as the pattern to follow.
