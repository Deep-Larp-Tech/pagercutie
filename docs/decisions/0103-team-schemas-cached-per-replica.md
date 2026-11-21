# ADR-0103: Team schemas and their validators are cached per replica

- **ID:** ADR-0103
- **Timestamp:** 2026-11-21T09:05+01:00
- **Status:** Accepted, amends ADR-0065 (query per event and per-event compilation replaced)
- **See:** SPEC §5.2, §5.3, §7, ADR-0063, ADR-0093, `backend/src/pagercutie/pipeline/ingest/stage.py`,
  `backend/src/pagercutie/pipeline/state.py`

## Decision

- `ingest.SchemaCache` holds each team's latest schemas, compiled, per replica. The first event of a team after a
  start or an invalidation queries `latest_team_schemas` and compiles the documents; later events read memory.
- Compiled validators are kept by schema version ID across invalidations: a version's document never changes
  (SCH-3), and versions are never deleted.
- `NOTIFY schemas_changed`, sent by `create_event_schema` (the only write to `event_schemas`), runs
  `state.schema_invalidator`, which clears the team lists. The listener runs it on every (re)connect, and
  `IngestState.drop_caches` clears them when the connection is lost (ADR-0063).
- A load that started before an invalidation returns what it read but does not store it, so a schema created
  while a query was in flight is seen by the next event.

Options considered:

| Option | Tradeoff |
|---|---|
| Query and compile per event (ADR-0065) | Always current. One query, one session and one compilation per team schema on every event, on the event loop. |
| **Cache invalidated by `NOTIFY`** (chosen) | The same mechanism as the catalog and rule set; a new schema applies once the replica receives the notification. |
| Cache with a TTL | No listener needed, but a new schema can be ignored for the TTL. |

## Rationale

- The pipeline architecture review flagged a session, a query and a compilation per team schema on every event, on
  the event loop. ADR-0065 chose the query when no invalidation path existed; `schemas_changed` now provides one.
- Reusing the listener keeps one fail-closed rule for every per-replica cache.
