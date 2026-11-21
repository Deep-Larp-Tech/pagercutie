# ADR-0043: Redis for shared state; Postgres decides

- **ID:** ADR-0043
- **Timestamp:** 2026-11-21T02:05+01:00
- **Status:** Accepted
- **Supersedes:** ADR-0007; amends ADR-0008
- **See:** SPEC §5.2, §5.3, §9, §10

## Decision

- Redis holds the state every replica must share on the hot path: dedup window claims (`SET NX EX`), occurrence
  counters (`INCR`, flushed to Postgres every 5 s) and per-recipient throttle buckets (one Lua script).
- A partial unique index on `(rule_id, fingerprint)` of non-resolved alerts keeps the alert upsert idempotent. A
  lost claim whose key is still `pending`, and every match while Redis is unreachable, take the Postgres upsert
  path; throttling then lets every delivery through.
- Cross-replica signals stay on Postgres `LISTEN/NOTIFY` (`rules_changed`, `schemas_changed`, `alert_changed`,
  `deliveries_pending`).
- `APP_REDIS_URL` configures the connection; compose and `mise run up` start `redis:8-alpine`.

## Rationale

- With requests spread round-robin, no replica owns a fingerprint or recipient, so per-key state cannot live in
  process memory (`NFR-2`).
- Redis answers "first in window" in one atomic round trip, keeping Postgres writes proportional to alerts.
- Falling back to Postgres makes Redis a throughput dependency, not a correctness one: an outage never loses or
  duplicates an alert.
- `NOTIFY` fires on commit, so listeners never act on a rolled-back change; Redis pub/sub would need the publish
  ordered after the commit by hand.
- Cost: `occurrences` can lose one flush batch when a replica dies; alert creation stays exact.
