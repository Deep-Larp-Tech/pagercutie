# ADR-0101: A resolved marker keeps Redis from counting on a resolved alert

- **ID:** ADR-0101
- **Timestamp:** 2026-11-21T09:05+01:00
- **Status:** Accepted, amends ADR-0043 (limit of the held path) and ADR-0077 (marker before the commit)
- **See:** SPEC §5.2, §13, `backend/src/pagercutie/core/redis.py`, `backend/src/pagercutie/pipeline/dedup/windows.py`,
  `backend/src/pagercutie/alerts/service.py`

## Decision

- `alerts.service.resolve_alert` calls `ResolvedWindows.mark_resolved(alert_id, rule_id, fingerprint)` after it
  updates the row and before the commit, while it holds the row lock. One Lua script sets
  `dedup:resolved:{alert_id}` for 86 400 s (the longest `window_s`) and deletes the window if it holds the alert.
- The claim script treats a window holding a marked alert as absent: it takes the window over (`Won`) and counts
  nothing. The confirm script deletes a window instead of storing a marked alert in it, which covers a confirm that
  arrives after the resolve.
- `ResolvedWindows` is a Protocol in `core/redis.py`, because entity packages may not import `pipeline`;
  `dedup.WindowStore` extends it and `RedisWindowStore` implements it. `create_app` puts the store on
  `app.state.windows`; the router injects it with `ResolvedWindowsDep`.
- Nothing resolves alerts automatically yet (no code writes `Resolution.AUTO`); the `RUN-5` resolve must call
  `mark_resolved` the same way.
- **Held-path limit.** A `Held` claim counts in Redis with no Postgres read; Postgres decides only on the upsert
  path. The counter flush locks its rows, applies counts to resolved alerts (the occurrences were counted before
  the marker reached Redis), drops counts of missing alerts, and logs and counts both in
  `dedup_stale_counters_total{reason}`. With Redis failing during the resolve, the window counts on the resolved
  alert until it expires; the flush reports those counts.

Options considered for the gap between the resolve and the window delete:

| Option | Tradeoff |
|---|---|
| Delete after the commit (ADR-0077) | Between the commit and the delete another replica gets `Held` and counts on the resolved alert, paging nobody for up to `window_s`. Needs an after-commit hook the request session does not have. |
| **Marker and delete before the commit** (chosen) | No gap: a match from then on takes the Postgres path, waits on the row lock, and opens a new alert once the resolve commits. If the commit fails, matches of that fingerprint take the Postgres path until the marker expires; correct, but more Postgres writes. |
| Marker read by a separate increment script | Works, but a held match would need a second round trip and a new claim variant for a refused count. |
| Delete from a `NOTIFY alert_changed` listener | Covers every resolve path, but adds a listener and a delay longer than the gap it closes. |

## Rationale

- The resolve must never let a recurrence count silently on a closed alert; the marker makes the claim decide that
  atomically on the Redis side.
- The flush is the one place where every held count meets the row, so it is where stale counts become visible.
