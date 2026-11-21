# ADR-0116: Both connection pools keep every connection open and skip pre-ping

- **ID:** ADR-0116
- **Timestamp:** 2026-11-22T10:05+01:00
- **Status:** Accepted
- **Amends:** ADR-0110 (pool defaults)
- **See:** ADR-0063, SPEC §5.1, `backend/src/pagercutie/core/db.py`, `backend/src/pagercutie/core/settings.py`

## Context

The engine used `pool_pre_ping=True` and overflow connections. Under `mise run demo:load` one replica opened 969 new
Postgres sessions in 120 s: an overflow connection is closed when returned and reopened on the next checkout, each
time with a TCP handshake and SCRAM-SHA-256 authentication on the replica's already saturated event loop. Tempo
`connect` spans (checkout including the pre-ping) were p50 110-134 ms under load and sit 3-4 times on the critical
path of every delivery. With this change and ADR-0115 on the pre-ADR-0110 code, new sessions in the same run fell
from 969 to 132 and UI delivery latency from p50 692 ms / p99 2.4 s to p50 190 ms / p99 438 ms.

## Decision

- **No overflow by default.** The request pool keeps 15 connections open (was 10 + 5 overflow) and the worker pool
  20 (was 10 + 10). The ceiling per replica stays 35, so `max_connections=200` in `compose.yaml` still fits five
  replicas, the migrate job and a few psql sessions (ADR-0110). Overflow stays configurable.
- **No pre-ping.** Checkout skips the extra round trip. `pool_recycle` replaces a connection older than 1800 s on
  checkout, so connections a proxy or firewall drops while idle are rare.

## After a Postgres restart

Every pooled connection is stale after Postgres restarts. The first query on one fails with
`InterfaceError: connection is closed`; the asyncpg dialect reports it as a disconnect and SQLAlchemy invalidates
the whole pool, so the other idle connections are replaced on their next checkout (checked against a real
Postgres 18 container). The ingest request that hits it answers `500` and the producer retries; the dispatcher,
executor and counter flush loops log, back off and retry; the listener (ADR-0063) reconnects with backoff and ingest
answers `503` until its caches reload.

## Options

| | Kept open, no pre-ping (chosen) | Overflow and pre-ping (before) | Kept open with pre-ping |
|---|---|---|---|
| Reconnects under load | None | One per overflow checkout | None |
| Round trips per checkout | 0 | 1 | 1 |
| After a Postgres restart | One failed query per replica, more for queries in flight | None | None |
| Idle connections held | 35 per replica | Up to 20 per replica | 35 per replica |

## Rationale

- Reconnects and pre-pings are paid on every delivery; a Postgres restart is rare, and every caller of a failed
  query already retries.
- The tradeoff: a Postgres restart costs each replica a failed ingest request or loop iteration, and 35 connections
  per replica stay open while idle.
