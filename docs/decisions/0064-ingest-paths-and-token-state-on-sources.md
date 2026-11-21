# ADR-0064: Ingest paths per source type and `has_token` on sources

- **ID:** ADR-0064
- **Timestamp:** 2026-11-21T03:42+01:00
- **Status:** Accepted
- **See:** SPEC §6, DOMAIN §7, ADR-0061

## Decision

- `sources.service.INGEST_PATHS` maps each source type that has an adapter to its route (`webhook` →
  `/ingest/{source_slug}`, `websocket` → `/ingest/{source_slug}/ws`). The adapters register their routes from it and
  `SourceRead.ingest_url` is rendered from it, so a WebSocket source shows its `/ws` URL. It replaces
  `INGESTIBLE_TYPES`; creating a source of a type without a path answers 422.
- `SourceRead.has_token` (added, additive): whether an ingest token exists. A source answers `404` on ingest until
  `POST /sources/{id}/token` runs, and the UI can now show that.
- A duplicate slug is detected with `INSERT … ON CONFLICT (slug) DO NOTHING RETURNING`, not by parsing the driver's
  `IntegrityError` text; the request's transaction stays usable without a savepoint.

## Rationale

- One table holds the route of each type, so the URL the API shows and the route the adapter serves cannot drift.
