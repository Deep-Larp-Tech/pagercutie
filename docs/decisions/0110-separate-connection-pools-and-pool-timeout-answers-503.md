# ADR-0110: Separate connection pools for requests and background loops; a pool timeout answers 503

- **ID:** ADR-0110
- **Timestamp:** 2026-11-21T09:03+01:00
- **Status:** Accepted
- **See:** SPEC §3.2, §5.1, ADR-0042, ADR-0084, `backend/src/pagercutie/core/db.py`, `backend/src/pagercutie/main.py`,
  `compose.yaml`

## Decision

Each replica creates two engines in `create_app`:

| Engine | Used by | Default size | Wait for a connection |
|---|---|---|---|
| Request | HTTP routes (management API, SSE, ingest) and the cache reloaders | 10 + 5 overflow | 2 s (`APP_DB_POOL_TIMEOUT_SECONDS`) |
| Worker | dispatch loop and channel adapters, counter flush, executor loop, the LISTEN connection | 10 + 10 overflow | 5 s (`APP_DB_WORKER_POOL_TIMEOUT_SECONDS`) |

`core/db.create_engine` takes a `PoolLimits`; the six values are settings. The worker sessionmaker reaches the
executor through `main.py`, so `pipeline/executor/worker.py` is unchanged.

A request that waits longer than the request pool timeout gets `sqlalchemy.exc.TimeoutError`. `main.py` maps it,
through the `DomainError` handler, to `Overloaded`: `503` with `Retry-After: 1`. `Overloaded` and `RateLimited`
(ADR-0111) carry `retry_after_s`; `handle_domain_error` sets the header for both.

One replica opens at most 10 + 5 + 10 + 10 = 35 connections. Postgres's default `max_connections` of 100 (97 for
non-superusers) fits two replicas, so `compose.yaml` starts Postgres with `max_connections=200`: five replicas
(175), the migrate job and a few psql sessions.

| Option | Tradeoff |
|---|---|
| **Second engine for background work** (chosen) | Hard isolation in both directions, no code in the loops. Two pools to size; idle connections of the worker pool count against `max_connections`. |
| Semaphore on the shared pool, capping background sessions | One pool. The cap lives in every loop that opens a session, including agent-owned `executor/worker.py`, and requests can still exhaust the pool and stall a completion after a send, which lets the lease expire and pages twice. |
| One shared pool, bigger | No starvation fix: a burst of ingest requests still queues the dispatcher's completions behind it. |

## Rationale

- SPEC §5.1 promised `503` on a pool timeout, but SQLAlchemy's default 30 s wait ended in a `500`.
- A completion that waits for a connection while its lease runs can let another replica send the delivery again.
  The worker pool's own timeout is part of the lease budget that ADR-0113's settings validator checks.
- The worker pool is sized for short holds: a dispatch send holds a connection only for the contact lookup and the
  completion, an executor step only for its completion, so 20 connections serve 16 sends and 20 steps.
- The defaults are not measured. The load-test plan (`docs/load-test-plan.md`) records the connection count per
  replica, which is what these numbers should be tuned against.
- Caddy is unchanged: it retries refused connections only, and a `503` with `Retry-After` is for the producer.
  `unhealthy_status 503` was rejected because one overloaded moment would take a replica out for `fail_duration`
  and push its load onto the others.
