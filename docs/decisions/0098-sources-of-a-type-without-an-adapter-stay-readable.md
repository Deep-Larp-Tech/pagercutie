# ADR-0098: Sources of a type without an adapter stay readable

- **ID:** ADR-0098
- **Timestamp:** 2026-11-21T09:30+01:00
- **Status:** Accepted
- **See:** SPEC §6, DOMAIN §7, ADR-0064

## Decision

- `SourceRead.ingest_url` for a type missing from `INGEST_PATHS` (today `protobuf`) is `/ingest/{slug}`. Ingest
  answers `404` there, as for any source of another type.
- `ingest_url` stays a required string; no contract field changes type.

## Rationale

- Backends before ADR-0064's create check (`d90573d`) accepted any `source_type`, so databases seeded then hold
  `protobuf` rows. `INGEST_PATHS[type]` raised `KeyError` on them and `GET /sources` failed for every user
  who could see one.
- Making `ingest_url` nullable would retype a contract field (SPEC §4.1). Hiding such rows from the list would
  leave them undeletable from the UI.
