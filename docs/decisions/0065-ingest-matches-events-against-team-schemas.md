# ADR-0065: Ingest matches each event against the team's schemas

- **ID:** ADR-0065
- **Timestamp:** 2026-11-21T04:20+01:00
- **Status:** Accepted, amended by ADR-0100 (team schemas and validators cached per replica, invalidated on `schemas_changed`)
- **See:** SPEC §4.1, §5.2, §7, DOMAIN §3, ADR-0061

## Decision

- Ingest no longer reads a schema from the source. For every event it queries the latest version of each schema the
  source's team owns (`event_schemas.service.latest_team_schemas`, one `DISTINCT ON (name)` query) and validates the
  payload against each with `jsonschema-rs` (draft 2020-12, offline).
- The most specific valid schema wins: most top-level `required` keys, then most top-level `properties`. No valid
  schema, or a tie at the top, rejects the event with `422 SCHEMA_UNRESOLVED`. Only the latest version of each
  `name` takes part.
- `schema_resolution` (fixed or discriminator) is removed from `SourceCreate`, `SourceUpdate`, `SourceRead`, the
  `sources` table (migration 0005 edited in place) and `IngestSource`. This breaks the additive rule of SPEC §4.1;
  accepted because no client outside this repository uses the API yet.
- `RejectReason.SCHEMA_INVALID` is removed: validation decides the match, so a failed validation is
  `SCHEMA_UNRESOLVED`. The planned per-replica schema cache and its `schemas_changed` signal are dropped.
- A stored schema that fails to compile is logged and never matches; validators are compiled per event.

## Rationale

- Producers send events without naming a schema, and a team configures schemas once instead of per source.
- A query per event always sees committed schemas, with no cache to reload; the cost is one indexed query per
  event, which the user chose over an in-memory cache.
- Ranking by required keys prefers the schema that asserts most about the event; rejecting ties keeps ingest from
  guessing between equally specific schemas.
- Offline compilation keeps a remote `$ref` from making ingest fetch URLs.
