# ADR-0099: The alert detail opens its own stream and reloads the run on `alert.updated`

- **ID:** ADR-0099
- **Timestamp:** 2026-11-21T09:07+01:00
- **Status:** Accepted
- **See:** ADR-0054, ADR-0088, SPEC §5.3, DOMAIN.md §6–§7, `frontend/src/hooks/use-alert-detail-stream.ts`,
  `backend/src/pagercutie/pipeline/executor/stage.py`

## Context

After a person marks a manual step done, `decide_step` answers with the next step still `pending`; the executor moves
it to `awaiting_manual` a moment later. Nothing told the browser: the executor sent no `alert_changed`, and the alert
detail had no stream (the feed's stream closes when the detail route replaces the feed). The next step's Mark as done
button (`RUN-3`) appeared only after a page reload.

## Decision

- **Backend.** `alert_changed` with `alert.updated` is also sent when `start_run` creates a run, when `decide_step`
  applies a decision, and when `complete_step` writes an outcome that changes the step's status, attempts, failures
  or result. A watched retry's re-claim every 5 s and a still-pending guard send nothing. Resolving already sends it.
- **Event type.** The existing `alert.updated` is reused, as the UI channel adapter does for a delivery row. No
  contract change.
- **Frontend.** `useAlertDetailStream` opens `GET /alerts/stream` (no `team_id`) for the open detail and ignores
  events for other alerts. An event for the alert merges into the `GET /alerts/{id}` cache with `mergeAlert` and
  reloads the run, deliveries and history. A reopened connection reloads all four; the first open does not, since
  they were just loaded. It replaces the effect that reloaded them when `status`, `occurrences` or escalations
  changed in a feed cache.
- The connect-and-backoff loop moved from `useAlertStream` to `lib/alert-stream.ts` (`openAlertStream`), shared by
  both hooks.

## Options

| | Reuse `alert.updated` (chosen) | New `alert.run_updated` type |
|---|---|---|
| Contract | Unchanged | Additive enum value; feed clients must accept it |
| Detail reloads per event | Run, deliveries, history | Run only |
| Batch dedup | Works as is | `feed_events` keeps one type per alert per batch, so it must send one event per (alert, type) or a run change next to an `alert.updated` is dropped |

| | Detail's own stream, filtered in the browser (chosen) | `alert_id` filter on the stream | One stream in the app layout |
|---|---|---|---|
| Contract | Unchanged | Additive query parameter | Unchanged |
| Traffic | Every visible alert's events | Only this alert's | Every visible alert's, one connection |
| Effort | One hook | Hook plus backend filter | Reworks ADR-0054's per-filter cache entries |

## Rationale

- Reusing the event and filtering in the browser fixes the bug without a contract change; the extra events are
  small and the detail ignores them.
- The `visible` check keeps the watched retry, which re-claims every 5 s for as long as the run has an unfinished step,
  from reloading open details on every poll.
