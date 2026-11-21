# ADR-0046: Dedup counters keyed by alert, one-round-trip claims, notification rounds on the alert

- **ID:** ADR-0046
- **Timestamp:** 2026-11-21T03:50+01:00
- **Status:** Accepted
- **See:** SPEC §5.2, §5.4, ADR-0043, ADR-0045

## Decision

- **Occurrence counters are keyed by alert:** the Redis hash `count:{alert_id}` holds `n` (count) and `seen` (newest
  `received_at`, epoch microseconds). One Lua script increments `n`, keeps the newer `seen` and adds the alert ID to
  `count:dirty`. The flush loop adds `n` to `occurrences` and moves `last_seen_at` forward to `seen`.
- **A claim is one round trip:** `SET key pending NX GET EX window_s` answers nothing when it won, otherwise the
  previous value (`pending` or the alert ID). A value that is neither goes down the Postgres path.
- **`alerts.notifications`** counts notification rounds: 1 when the alert opens, one more per `Renotified`. It is the
  `notification_seq` in `Renotified` and part of the deterministic delivery ID. Server default 1, so replicas
  running the previous version keep inserting alerts.
- **The Redis client times out after 0.5 s** (connect and read), then the match takes the Postgres path.
- The unique index is on `fingerprint` alone, as the model and migration 0008 have it. SPEC and ADR-0043 said
  `(rule_id, fingerprint)`; the fingerprint hashes the rule ID, so the two are equivalent and SPEC now matches the
  code.

Options considered for the counter key:

| Option | Tradeoff |
|---|---|
| `count:{rule_id}:{fingerprint}` (SPEC before) | The flush must look up the alert; if it was resolved in between, the count goes to the next alert of that fingerprint or nowhere. |
| **`count:{alert_id}`** (chosen) | `Held` already carries the alert ID; the flush is `UPDATE … WHERE id`. |

Options considered for `last_seen_at` on the Redis path:

| Option | Tradeoff |
|---|---|
| Flush sets `last_seen_at = now()` | No extra Redis state; off by up to the 5 s flush interval. |
| **Redis keeps the newest `received_at`** (chosen) | Exact event time; needs the Lua script so count and time change together. |

## Rationale

- The user confirmed both changes to SPEC §5.2.
- `SET … NX GET` (Redis 7+) removes the gap between `SET NX` and `GET` in which an expiring key would turn a real
  win into `Pending`.
