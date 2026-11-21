# ADR-0078: The counter flush drains atomically and restores on failure

- **ID:** ADR-0078
- **Timestamp:** 2026-11-21T06:20+01:00
- **Status:** Accepted
- **See:** SPEC §5.2, §9, ADR-0020, ADR-0074

## Decision

- `WindowStore.drain(limit)` is one Lua script: `SPOP` up to `limit` alert IDs from `count:dirty`, `HMGET` and
  `DEL` each counter. `WindowStore.restore(counters)` adds counters back with the same script `increment` uses.
- `flush_counters` drains batches of 500 and applies each in one transaction (`dedup.apply_counters`: one
  `UPDATE … FROM (VALUES …)` plus `NOTIFY alert_changed`). A batch whose transaction fails is restored and the
  error propagates; the loop logs it and tries again at the next tick.
- The loop flushes every 5 s and once more after the stop signal, before the lifespan closes Postgres and Redis.
- The worker is built in `create_app`, because it needs the sessionmaker and the window store.

Options considered for a failed transaction:

| Option | Tradeoff |
|---|---|
| Drop the batch (SPEC before) | Simplest. A database outage loses every count drained during it, and the ADR-0020 retry guard reads `occurrences`. |
| **Restore the batch to Redis** (chosen) | One more store method; counts wait out the outage. A crash between drain and commit still loses one batch. |
| Read, commit, then subtract | Nothing lost on a crash, but a crash after the commit counts the batch twice, and claiming IDs without `SPOP` lets two replicas apply the same counter. |

## Rationale

- The user put the flush loop in scope (stage 5 of the dedup plan).
- Counts feed the failed-retry guard (ADR-0020), so an outage should delay them, not drop them.
