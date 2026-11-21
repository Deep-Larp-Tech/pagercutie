# ADR-0061: Source adapters and ingest replies

- **ID:** ADR-0061
- **Timestamp:** 2026-11-21T03:30+01:00
- **Status:** Accepted, amended by ADR-0064 (`INGEST_PATHS` replaces `INGESTIBLE_TYPES`) and ADR-0091 (rule set loaded)
- **See:** SPEC §5.1, §5.5, §6, §7, DOMAIN §7, ADR-0042, ADR-0045, ADR-0062

## Decision

- **Interface:** `pipeline/adapters.py` defines `SourceAdapter` (a `type: SourceType` and a `router()`). An
  adapter turns its transport into a `RawEvent` and calls `orchestrator.process_event`. It sits outside the stage
  packages because stages may not import the orchestrator. `ADAPTERS` lists the adapters;
  `sources.service.INGESTIBLE_TYPES` lists the types that have one, and a unit test keeps the two equal. Creating
  a source of another type (`protobuf` today) answers 422.
- **`RawEvent.source_type`** (added): the adapter's type. `ingest.authenticate` answers 404 when it differs from the
  source's type, so a webhook source cannot be fed through the WebSocket path.
- **`SourceCatalog.sources` holds `IngestSource`**, not `SourceRead`: authentication needs the token hash, which
  no API DTO carries.
- **Normalising:** `ingest.normalise` authenticates, decodes the body as a JSON object (`UNDECODABLE` otherwise),
  resolves the schema (fixed or discriminator, `SCHEMA_UNRESOLVED` otherwise) and maps the severity. The body is
  decoded as JSON whatever its content type; `RawEvent.content_type` selects a decoder once the protobuf adapter
  exists. JSON Schema validation (`SCHEMA_INVALID`) comes with the schema cache.
- **Webhook replies** (`POST /ingest/{slug}`): `202 IngestResult` once committed, `422` from `EventRejected`,
  `401` missing or wrong token, `404` unknown or disabled slug or another type, `503` before the first catalog
  load. The token is checked before the body is read.
- **WebSocket** (`/ingest/{slug}/ws`): the handshake is denied with the status the webhook would answer. Each text
  or binary frame is one event, handled in order; the reply frame is the `202` body, or `{"status", "detail"}`.
  Every frame re-checks the source, so a rotated token or a disabled source closes the connection with `1008`.
- Until rule loading and the Redis window store exist, `app.state.rule_set` and `app.state.window_store` are
  `None` and authenticated events answer `501`.

Considered and rejected:

| Option | Why not |
|---|---|
| Adapters inside `pipeline/ingest` | The ingest stage would import the orchestrator, which import-linter forbids. |
| Close the WebSocket on a rejected frame | One bad event would cost the producer its connection and the frames after it. |
| Allow `protobuf` sources before their adapter | A source that can never receive events. |
| Reject non-JSON content types | Every adapter delivers JSON today, and `curl -d` sends `application/x-www-form-urlencoded`. |

## Rationale

- `ING-2`: a new source type is one class plus one tuple entry; authentication, decoding, resolution and the
  pipeline are shared.
