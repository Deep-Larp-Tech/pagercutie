# ADR-0103: Each replica keeps a fixed pool of 15 Postgres connections without pre-ping

- **ID:** ADR-0103
- **Timestamp:** 2026-11-21T10:20+01:00
- **Status:** Accepted
- **See:** ADR-0063, ADR-0097, SPEC §3.2, §5.1, §12.2, `backend/src/pagercutie/core/db.py`,
  `backend/src/pagercutie/core/settings.py`, `compose.yaml`

## Context

`create_engine` used SQLAlchemy's defaults with `pool_pre_ping=True`: 5 pooled connections plus 10 overflow
connections, and a `SELECT 1` on every checkout. Under `mise run demo:load` one replica opened 969 new Postgres
sessions in 120 s. Connections above 5 are overflow, closed when returned and reopened on the next checkout, each
with a TCP handshake and SCRAM-SHA-256 authentication on the replica's already saturated event loop. Tempo `connect`
spans (checkout including the pre-ping) were p50 110-134 ms under load and sit 3-4 times on the critical path of
every delivery.

## Decision

- **Pool.** `APP_DB_POOL_SIZE` (default 15) connections stay open; `APP_DB_MAX_OVERFLOW` (default 0) more are opened
  on demand. The ceiling per replica stays 15, as before, but a busy replica no longer reconnects.
- **No pre-ping.** Checkout skips the extra round trip. `pool_recycle` replaces a connection older than 1800 s on
  checkout, so connections that a proxy or firewall drops while idle are rare.
- **Postgres.** `compose.yaml` starts Postgres with `max_connections=200`: 10 replicas (the `BACKEND_PORTS` range,
  ADR-0097) × 15 = 150, plus `migrate`, `psql` and the superuser reserve. The default of 100 would refuse
  connections from the seventh replica on once every pool is full.
- **Rule.** Replicas × (`db_pool_size` + `db_max_overflow`) must stay under Postgres `max_connections` minus
  headroom. A deployment that raises one raises or checks the other.

## After a Postgres restart

Without pre-ping, every pooled connection is stale after Postgres restarts. The first query on one fails with
`InterfaceError: connection is closed`; the asyncpg dialect reports it as a disconnect, and SQLAlchemy invalidates
the whole pool, so every other idle connection is replaced on its next checkout. Checked against a real Postgres 18
container: with 3 idle connections, the first query after `docker restart` failed and the next three succeeded.

Each loop survives that one failure:

| Who hits the stale connection | What happens |
|---|---|
| Ingest request (§5.1) | Answers `500`; the producer retries, and dedup folds the retry into the same alert |
| Dispatcher (`dispatch/worker.py`) | `dispatch_loop` logs and polls again after 1 s; a claimed delivery whose completion failed is sent again after its 30 s lease |
| Executor (`executor/worker.py`) | `executor_loop` logs and polls again after 1 s; `_execute` catches a failed step |
| Counter flush (`dedup/worker.py`) | `flush_counters` puts the batch back in Redis; the loop logs and flushes again after 5 s |
| Listener (`core/listen.py`) | The termination listener or the 10 s heartbeat ends the connection, which is invalidated; `on_lost` makes ingest answer `503` until the reconnect reloads the caches. Its driver-level calls bypass SQLAlchemy's disconnect detection, so a stale connection taken on reconnect fails `LISTEN` and costs one more backoff step (0.5 s, then 1 s), until a query from another loop has invalidated the pool |

## Options

| | Fixed pool, no pre-ping (chosen) | Defaults with pre-ping (before) | Fixed pool with pre-ping |
|---|---|---|---|
| Reconnects under load | None | One per overflow checkout | None |
| Round trips per checkout | 0 | 1 | 1 |
| After a Postgres restart | One failed query per replica, more for queries already in flight | None | None |
| Idle connections held | Up to 15 per replica | Up to 5 per replica | Up to 15 per replica |

## Rationale

- The reconnects and the pre-ping are paid on every delivery; a Postgres restart is rare, and every caller of a
  failed query already retries.
- The tradeoff: a Postgres restart costs each replica one failed ingest request or loop iteration (more if several
  queries were in flight), and 15 connections per replica stay open while idle, so `max_connections` has to cover
  replicas × 15.
