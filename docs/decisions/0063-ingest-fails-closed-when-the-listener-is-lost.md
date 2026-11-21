# ADR-0063: Ingest fails closed when the listening connection is lost

- **ID:** ADR-0063
- **Timestamp:** 2026-11-21T03:40+01:00
- **Status:** Accepted
- **See:** SPEC §5.3, §6, ADR-0062

## Decision

- **Connection:** `core/listen.py` takes its listening connection from the app's SQLAlchemy engine
  (`engine.connect()`, then the asyncpg driver connection), so it shares the engine's DSN, connect arguments and
  telemetry. It is invalidated on exit, never returned to the pool still subscribed to the channels. It holds one
  pool slot per replica.
- **Heartbeat:** with no notification for 10 s the listener runs `SELECT 1` (5 s timeout). A half-open connection
  never reports its loss; the heartbeat turns it into a reconnect within about 15 s.
- **Fail closed:** a lost connection, a failed heartbeat or a failed handler calls `on_lost`, which drops the
  source catalog (`IngestState.drop_catalog`). Ingest then answers `503`, and an open WebSocket closes with `1013`
  on its next frame, until the reconnect reloads the catalog. A rotated token or a disabled source never keeps
  working on a replica that cannot hear the change.
- **Failures stay inside the listener:** `listen()` catches every `Exception`, logs it and reconnects with backoff
  (0.5 s to 30 s). A handler error no longer stops the worker, which would shut the replica down (`run_workers`).
- **Unreadable rows:** `load_ingest_sources` validates each row's `schema_resolution` and `severity` itself and
  skips (and logs) a row that fails, so one bad source answers `404` instead of blocking every other source.
- `/health` is unchanged: it does not report whether the catalog is loaded.

Considered and rejected:

| Option | Why not |
|---|---|
| Fail open (keep the last catalog) | A rotated token or a disabled source keeps working for up to the reconnect backoff, or indefinitely on a half-open connection. |
| Own `asyncpg.connect` | Duplicates the engine's DSN and settings and skips its instrumentation. |
| `/health` answers 503 until the catalog loads | Not wanted: `/health` keeps its meaning (process and database up). |
| Periodic full reload instead of a heartbeat | Queries every source on every replica on a timer; the heartbeat costs one `SELECT 1`. |

## Rationale

- `POST /sources/{id}/token` revokes the previous token; with per-replica caches only failing closed makes that hold
  while a replica is cut off from notifications.
