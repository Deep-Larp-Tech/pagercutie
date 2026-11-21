# ADR-0093: Resolving an alert closes its runbook run

- **ID:** ADR-0093
- **Timestamp:** 2026-11-21T08:05+01:00
- **Status:** Accepted, amends ADR-0090 (watching also ends on resolve)
- **See:** SPEC §11.3, DOMAIN.md §6, `backend/src/pagercutie/alerts/service.py`

## Decision

- `alerts.service.close_run` runs in the resolve transaction, under the alert's row lock. It locks the run's step
  runs, marks every unfinished step (`pending`, `awaiting_*`, `running`) `skipped` and sets `run_at` to null on every
  step, which also ends a succeeded retry's watch.
- Each skipped step is audited as `step.skipped` with the resolving user as actor and `"reason": "resolved"` in
  `data`; `runbook_run.finished` is audited once, by the same user, when a step was skipped. A run that had already
  finished gets no new entries.
- It lives in the alerts package, not the executor stage, because entity packages may not import the pipeline
  (import-linter). The executor's outcome `UPDATE` is conditional on the lease and status, so an outcome that arrives
  after the resolve is dropped as stale.
- The executor's claim still parks steps of resolved alerts, for runs resolved before this change and any future
  resolve path that does not call `close_run`.

## Rationale

- `RUN-5`: the run records what was done and by whom and ends with the alert, instead of leaving steps waiting for
  approvals nobody can give.
