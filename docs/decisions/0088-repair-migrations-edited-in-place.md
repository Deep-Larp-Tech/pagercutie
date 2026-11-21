# ADR-0088: Repair migrations edited in place with an idempotent migration

- **ID:** ADR-0088
- **Timestamp:** 2026-11-21T14:00+01:00
- **Status:** Accepted
- **See:** SPEC §12.2, ADR-0068, `backend/migrations/versions/0018_repair_edited_migrations.py`

## Decision

- An applied migration is never edited. A schema change goes into a new revision.
- 0005 and 0006 are restored to their content before they were edited (409c0af dropped
  `sources.schema_resolution`; c87c524 added `runbooks.deleted_at` and replaced `uq_runbooks_slug` with the
  partial index `ix_runbooks_slug`).
- Revision 0018 applies those changes with `IF EXISTS` / `IF NOT EXISTS`, so every database reaches the same head:
  ones migrated before the edits, ones built from the edited files, and new ones.

## Rationale

- Alembic tracks only the revision ID. A database already past 0006 never ran the edited file, so it had no
  `runbooks.deleted_at` (`GET /runbooks` failed with `column runbooks.deleted_at does not exist`) and kept the
  `NOT NULL` `sources.schema_resolution` column the model no longer writes.
- Alternatives: keep the edited files and tell everyone to drop their database (loses local data, and breaks again
  on any deployed database), or add a plain non-idempotent 0018 (fails on databases built from the edited files).
