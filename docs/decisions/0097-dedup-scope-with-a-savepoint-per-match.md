# ADR-0097: One dedup scope per event, a savepoint per match

- **ID:** ADR-0097
- **Timestamp:** 2026-11-21T09:05+01:00
- **Status:** Accepted
- **See:** SPEC §5.2, §5.5, §13, ADR-0043, ADR-0076, `backend/src/pagercutie/pipeline/dedup/stage.py`,
  `backend/src/pagercutie/pipeline/orchestrator.py`

## Decision

- **Scope.** `dedup.deduplicate(matches, windows)` is an async context manager. On entry it claims every match's
  window in one Lua call (`WindowStore.claim` takes a list) and splits the matches into `repeated` (held windows)
  and `to_record`. On a normal exit it confirms the windows of committed outcomes and releases the other won
  windows, one call each. On any exception, `CancelledError` included, it releases every won window. A failure
  during the claim call releases whatever the call stored for the event. The orchestrator no longer holds the
  claim, record, confirm and release sequence.
- **Pending token.** A won window holds `pending:{event_id}` instead of `pending`. Confirm and release change a
  window only while it still holds that token, so they never touch a window that expired and another event won.
- **Held counts in the claim.** The claim script counts the occurrence on a held window in the same step, so a
  held match costs one round trip and `repeat`/`increment` are gone.
- **Savepoint per match (user decision).** The orchestrator records each `to_record` match inside
  `session.begin_nested()`. If `record`, `route` or `start_run` raises an `Exception`, that savepoint rolls back,
  the scope releases the match's window, `matches_failed_total` counts it, `pipeline.match_failed` logs it with
  `event_id` and `rule_id`, and the other matches commit; the source still gets `202`. A `BaseException` that is not
  an `Exception` aborts the event.
- **Lock order.** `to_record` is sorted by rule ID, then fingerprint, inside the scope, where the locks are taken;
  `evaluate` no longer sorts. The counter flush locks rows in the same order (ADR-0098).
- **TTL of a won repeat.** `record` returns the alert's `notified_at`. A won window whose match is `Repeated` is
  confirmed with a TTL of `notified_at + window_s - now`, and released when that is not positive. `Opened` and
  `Renotified` keep the claim's TTL, since their round starts at this event.
- **Observability.** The scope counts committed outcomes in `dedup_outcomes_total{outcome,path}` and opened alerts
  in `alerts_created_total`; evaluation counts `events_unmatched_total`. The orchestrator binds `event_id` into the
  structlog context, logs one `pipeline.event_processed` line per event (source, schema, matched rule IDs, outcomes,
  failed rule IDs) and opens a span per in-request stage.

Options considered for a failing match:

| Option | Tradeoff |
|---|---|
| Fail the event (before) | Simplest. One bad template or recipient turns every event of that schema into `500`, and the producer retries forever. |
| **Savepoint per match** (chosen) | One `SAVEPOINT` per recorded match. A broken rule loses its own alerts, visibly in a metric and a log, and the others are delivered. |
| A transaction per match | No shared rollback, but `202` would no longer mean "everything committed" and each match costs a commit. |

Options considered for the window TTL after a won repeat:

| Option | Tradeoff |
|---|---|
| Keep the claim's TTL (before) | After a Redis restart or clock skew, renotification waits up to a full `window_s` longer. |
| **Remainder of the alert's round** (chosen) | One more returned column; the window ends when the row says the round ends. |
| Release the window | Every following match takes the Postgres path until one renotifies. |

## Rationale

- The scope keeps dedup's state machine in the dedup stage, and claiming inside it closes the gap in which a failed
  second claim left the first window `pending` for `window_s`.
- One script call per phase keeps the per-claim result types and turns N round trips into one.
