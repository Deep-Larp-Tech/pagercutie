# ADR-0068: Soft delete runbooks

- **ID:** ADR-0068
- **Timestamp:** 2026-11-21T14:00+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §3, §7, ADR-0031, ADR-0057

## Decision

- Deleting a runbook sets `runbooks.deleted_at`; the row stays. List, get, update and delete ignore deleted
  runbooks and answer `404`.
- The slug is unique among active runbooks only (partial unique index `ix_runbooks_slug` on
  `slug WHERE deleted_at IS NULL`), so a slug can be reused after its runbook is deleted.
- Deleting a runbook detaches the rules that used it (`rules.runbook_id` set to null, `NOTIFY rules_changed`), so
  new alerts no longer start it. Runbook runs keep pointing at the row and keep the steps they copied.
- Deleting a team ignores its deleted runbooks and removes them with the team, unless one of them has runs (`409`).
- Create, update and delete write `runbook.created`, `runbook.updated` and `runbook.deleted` audit entries.
  `runbook.updated` holds `before` and `after` of the changed fields (`title`, `format`, `original`, `attach`);
  `runbook.deleted` holds the slug, title and `detached_rule_ids`.

## Rationale

- `rules.runbook_id` and `runbook_runs.runbook_id` are `ON DELETE RESTRICT`: a hard delete fails for any runbook a
  rule uses or that ever ran, and `SET NULL` or cascades would lose which runbook a run followed (`RUN-5`).
- Alternatives: answer `409` while referenced (no migration, but a runbook that ever ran can never be deleted), or
  make `runbook_runs.runbook_id` nullable with `SET NULL` (loses history). The user chose soft delete.
