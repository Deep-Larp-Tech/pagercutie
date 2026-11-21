# ADR-0101: Adapters authenticate once and pass the authenticated source

- **ID:** ADR-0101
- **Timestamp:** 2026-11-21T09:05+01:00
- **Status:** Accepted, amends ADR-0061 (`RawEvent` fields, schema resolution text, window store `501`)
- **See:** SPEC §4.2, §5.5, §6, ADR-0065, `backend/src/pagercutie/pipeline/adapters.py`,
  `backend/src/pagercutie/pipeline/state.py`, `backend/src/pagercutie/pipeline/messages.py`

## Decision

- `RawEvent` is `source: IngestSource` (the source the adapter authenticated) and `body: bytes`. `source_slug`,
  `source_type`, `token` and `content_type` are removed: the bearer secret no longer travels through the
  pipeline, and nothing read `content_type`. `ingest.normalise(raw, load_schemas)` decodes and resolves; it no
  longer authenticates.
- The webhook authenticates once per request. The WebSocket authenticates at the handshake and again only when the
  catalog object changed since, since every reload swaps the whole catalog; a rotated token or a disabled source
  still closes the connection with `1008` on the next frame.
- Bodies are JSON. SPEC §4.2 makes an adapter for another wire format convert to JSON before building the
  `RawEvent`, so no content type reaches the pipeline.
- `IngestState`, the cache accessors and the reloaders move to `pipeline/state.py`. `window_store` and `schemas` are
  required fields; the `NotImplementedYet` path for a missing window store is gone.
- `adapters.ingest_router()` builds the router of every ingest route; dependencies shared by all ingest routes are
  declared there.

Options considered for `content_type`:

| Option | Tradeoff |
|---|---|
| **Remove it** (chosen) | Matches SPEC §4.2 (adapters deliver JSON); a protobuf adapter converts in the adapter. |
| An enum that `decode` matches exhaustively | Type-safe, but moves decoding of every format into ingest, against SPEC §4.2, for a format no adapter receives. |

## Rationale

- One authentication per event, and a message that carries what was proven (the source) instead of the secret
  that proved it.
- `IngestState` is replica cache state, not transport; separating it leaves `adapters.py` with transports and
  their metrics.
