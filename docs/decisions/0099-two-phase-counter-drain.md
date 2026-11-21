# ADR-0099: The counter flush drains in two phases

- **ID:** ADR-0099
- **Timestamp:** 2026-11-21T09:05+01:00
- **Status:** Accepted, supersedes ADR-0078
- **See:** SPEC §5.2, §9, ADR-0020, ADR-0090, `backend/src/pagercutie/pipeline/dedup/windows.py`,
  `backend/src/pagercutie/pipeline/dedup/worker.py`

## Decision

- `flush_counters` names each batch (`uuid4`) before draining it. `drain(batch, limit)` is one Lua script: `SPOP`
  up to `limit` IDs from `count:dirty`, move each counter into the hash `count:batch:{batch}` as `n:seen`, and add
  the batch to the sorted set `count:batches` scored by the Redis clock (`TIME`).
- After the transaction commits, `ack(batch)` deletes the batch. If it fails, `restore(batch)` adds the batch back
  to the counters from Redis, so the counts never pass through a Python list that a crash would lose.
- Every flush first calls `recover(60)`, which restores every batch drained at least 60 s ago (12 flush intervals):
  batches of a replica that died, of a drain whose reply timed out, or of a restore that failed.
- Every store method degrades on any `redis.RedisError`, `ResponseError` (`READONLY`, `OOM`) included, not only on
  connection and timeout errors.

Options considered:

| Option | Tradeoff |
|---|---|
| Drain and delete, restore from memory (ADR-0078) | A drain reply lost to the 0.5 s timeout, or a replica dying before the commit, loses the batch. |
| **Batch key, ack after commit, recover by age** (chosen) | Nothing is lost while Redis keeps its data. A flush slower than 60 s between drain and ack, or an ack that fails after the commit, counts the batch twice. |
| Per-replica processing key recovered on start | Needs a stable replica identity; a replica scaled away never starts again to recover its key. |

## Rationale

- `occurrences` feeds the failed-retry guard (ADR-0020, ADR-0090). Losing counts hides a failed retry; counting a
  batch twice can report one more failure. The chosen design makes loss need a Redis data loss and makes a double
  count need a flush that stalls for a minute or an ack lost after its commit, both logged
  (`dedup.batches_recovered`, `dedup.batch_not_acked`).
- The Redis clock scores batches, so replica clock skew cannot recover a batch early.
