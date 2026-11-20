# ADR-0002: PostgreSQL with jsonb, not MongoDB

- **ID:** ADR-0002
- **Timestamp:** 2026-11-20T20:20+01:00
- **Status:** Accepted
- **See:** SPEC §3.3, §12.2

## Decision

PostgreSQL 18 is the database. Event payloads, rule ASTs and schemas are stored in `jsonb` columns.

## Rationale

- The team knows Postgres; with 12 hours left, experience matters most.
- Schemas are runtime data and validated in code anyway, so Mongo's flexible documents add little.
- Postgres also gives transactions, `SKIP LOCKED` job tables, unique-index upserts and `LISTEN/NOTIFY` without extra infrastructure.
