# ADR-0062: Source catalog reloaded on NOTIFY over one listening connection

- **ID:** ADR-0062
- **Timestamp:** 2026-11-21T03:35+01:00
- **Status:** Accepted, amended by ADR-0063 (connection from the engine, heartbeat, catalog dropped when the connection is lost)
- **See:** SPEC §5.2, §5.3, §6, ADR-0043, ADR-0061

## Decision

- Each replica keeps the `SourceCatalog` (enabled sources with an ingest token, by slug) in
  `app.state.source_catalog`. Ingest requests never query Postgres for sources.
- Every write in `sources.service` runs `pg_notify('sources_changed', '')` in its transaction, so the notification
  goes out only on commit.
- `core/listen.py` provides the replica's one listening connection: `listen_worker(settings, {channel: handler})`.
  It runs every handler after each (re)connect, which covers notifications sent while disconnected, and the
  channel's handler after each notification. A burst collapses into one call, and a handler shared by several
  channels runs once. After a lost connection or a failed handler it reconnects with exponential backoff (0.5 s to
  30 s). `rules_changed` and `schemas_changed` add their handlers to the same map.
- Ingest answers `503` until the first load.

Considered and rejected:

| Option | Why not |
|---|---|
| Query Postgres per request | Puts Postgres on the hot path of every event. |
| Cache with a TTL | Token rotation and disabling would take up to the TTL to apply, while `POST /sources/{id}/token` promises the old token stops immediately. |
| One connection per channel | SPEC §5.3 gives each replica one listening connection. |
