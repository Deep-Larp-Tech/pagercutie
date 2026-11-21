# ADR-0096: Schema validation answers every issue with `200`

- **ID:** ADR-0096
- **Timestamp:** 2026-11-21T08:05+01:00
- **Status:** Accepted
- **See:** SPEC §7, DOMAIN.md §7, `backend/src/pagercutie/event_schemas/service.py`

## Decision

- `POST /event-schemas/{schema_id}/validate` is open to any authenticated user and answers `404` for an unknown
  schema. Otherwise it answers `200 {valid, issues}`; an invalid payload is `valid: false`, not `422`.
- `issues` lists every error `jsonschema-rs` finds (`iter_errors`), each with an RFC 6901 pointer into the payload
  (`""` for the root) and the library's message.
- The schema compiles offline, as in ingest. A stored schema that does not compile answers one issue at `""`
  instead of a `500`.

## Rationale

- The endpoint answers a question about the payload; `422` is reserved for a request body the API cannot accept.
- All issues at once let the schema editor show every problem in one round trip.
