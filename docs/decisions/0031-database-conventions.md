# ADR-0031: Database conventions

- **ID:** ADR-0031
- **Timestamp:** 2026-11-20T22:12+01:00
- **Status:** Accepted
- **See:** SPEC §12.2

## Decision

- **Enums** are Postgres enum types whose labels are the enum's values (`str_enum` in `core/models.py`), one type
  per Python enum. `alembic check` misses added values, so adding one needs a hand-written
  `ALTER TYPE … ADD VALUE` migration; a migration that also uses the new value runs the `ADD VALUE` in
  `op.get_context().autocommit_block()`. `downgrade()` drops each type after its table, because `op.drop_table`
  leaves it behind. A migration that adds a column of an existing type declares it as
  `postgresql.ENUM(name=…, create_type=False)`.
- **Deletes:** foreign keys to owned configuration and to history are `ON DELETE RESTRICT` (the service answers
  `409`). Only pure children cascade: memberships, rotations and their slots, sessions, step runs.
- **Value objects** (channel preferences, schema resolution, rule parts, runbook steps, alert fields) are typed
  `jsonb` (ADR-0030). Channel preferences are a column on `users` and on `teams`.
- **ID lists** without a foreign key are `uuid[]`: `rules.schema_ids` (event schemas are never deleted) and
  `alerts.escalated_team_ids` (GIN-indexed for team feeds). Rotation members are a table, so deleting a user removes
  them from the rotation.
- **`audit_log`** has no foreign keys: history outlives the users, teams and entities it names.
- **Secrets** (ingest tokens, session cookies) are stored as SHA-256 hashes.
- **Timestamps** are `timestamptz` set by the database; `updated_at` only where the DTO exposes it.
- **Migrations:** the first migration of each entity module is its own revision (`0001_users` … `0009_audit_log`),
  numbered in foreign-key order.

## Rationale

- Native enums sort in declaration order, so SQL can filter and order by severity (`severity >= 'warn'`), and
  `psql` and tbls show the allowed values on the column type. Postgres cannot remove an enum value; contract
  changes are additive (SPEC §4.1), so no migration needs to.
- RESTRICT keeps alert history and running runbook runs consistent; deleting a referenced row answers `409`.
- Arrays keep the evaluator's rule cache a single-table read where foreign keys would add nothing.
