# ADR-0031: Database conventions

- **ID:** ADR-0031
- **Timestamp:** 2026-11-20T22:12+01:00
- **Status:** Accepted
- **See:** SPEC §12.2

## Decision

- **Enums** are `varchar` + CHECK constraint holding the values (`str_enum` in `core/models.py`), not native
  Postgres enums. `alembic check` does not compare CHECK constraints, so adding a value needs a hand-written
  migration that replaces the constraint.
- **Deletes:** foreign keys to owned configuration and to history are `ON DELETE RESTRICT` (the service answers
  `409`). Only pure children cascade: memberships, rotations and their slots, sessions, step runs.
- **Value objects** (channel preferences, schema resolution, rule parts, runbook steps, alert fields) are typed
  `jsonb` (ADR-0030). Channel preferences are a column on `users` and `teams`, not a table.
- **ID lists** without a foreign key are `uuid[]`: `rules.schema_ids` (event schemas are never deleted) and
  `alerts.escalated_team_ids` (GIN-indexed for team feeds). Rotation members are a table, so deleting a user removes
  them from the rotation.
- **`audit_log`** has no foreign keys: history outlives the users, teams and entities it names.
- **Secrets** (ingest tokens, session cookies) are stored as SHA-256 hashes.
- **Timestamps** are `timestamptz` set by the database; `updated_at` only where the DTO exposes it.
- **Migrations:** the first migration of each entity module is its own revision (`0001_users` … `0009_audit_log`),
  numbered in foreign-key order.

## Rationale

- Native enum values cannot be removed and are awkward to add in a transaction; a CHECK is swapped in one.
- RESTRICT keeps alert history and running pipelines consistent; the user gets a clear `409` instead of silent loss.
- Arrays keep the evaluator's rule cache a single-table read where foreign keys would add nothing.
