# ADR-0100: Ingest caches compiled event schema validators by schema version ID

- **ID:** ADR-0100
- **Timestamp:** 2026-11-21T12:00+01:00
- **Status:** Accepted
- **Amends:** ADR-0065 ("validators are compiled per event")
- **See:** SPEC §7, `backend/src/pagercutie/pipeline/ingest/stage.py`, `backend/src/pagercutie/core/log.py`,
  `backend/src/pagercutie/core/telemetry.py`

## Context

Under `mise run demo:load` one backend replica (one uvicorn process, one event loop) is CPU-bound at about
360 events/s with OpenTelemetry on and 640 events/s with it off, while Postgres sits at 15-25% CPU. A saturated loop
delays every await: UI delivery latency is p50 690 ms / p99 2.4 s under load against 31 ms idle. Ingest compiled a
`jsonschema_rs.Draft202012Validator` for every schema of the team on every event.

## Decision

- `ValidatorCache` in `pipeline/ingest/stage.py` keeps compiled validators by `TeamSchema.id`, one per replica,
  bounded at 4096 entries with least-recently-used eviction. A schema that does not compile is cached as `None`: it
  is logged once per cache entry and never matches.
- The ID is a sufficient key because event schema rows are immutable: `json_schema` is written only at create, and a
  new version is a new row with a new ID. No invalidation or `NOTIFY` is needed.
- ADR-0065's one `latest_team_schemas` query per event stays; only compilation is cached. A new version still takes
  effect on the next event after its commit.
- Same change, same goal: `RequestLoggingMiddleware` (`core/log.py`) is a pure ASGI middleware instead of
  `app.middleware("http")`, whose `BaseHTTPMiddleware` adds a task group and response wrapping per request; behaviour
  is unchanged. `FastAPIInstrumentor.instrument_app` gets `exclude_spans=["receive", "send"]`, dropping the internal
  `http receive` / `http send` spans of every request. Sampling is unchanged.

## Options

| | Bounded LRU dict keyed by ID (chosen) | `functools.lru_cache` | Unbounded dict | Cache the schema rows too |
|---|---|---|---|---|
| Key | Schema ID, schema passed alongside | Needs hashable arguments; `json_schema` is a dict | Schema ID | Team ID |
| Memory | Capped | Capped | Grows with every version ever seen | Capped |
| Compile failure | Cached as `None`, logged once | Exceptions are not cached, so logged every event | Cached as `None` | Cached as `None` |
| Freshness | Query per event (ADR-0065) | Same | Same | Needs invalidation on schema create |

## Rationale

- Compilation is the per-event CPU cost that does not depend on the payload; validating with a compiled validator is
  cheap.
- Immutability of schema versions makes an ID-keyed cache always correct, so it keeps ADR-0065's guarantee that
  ingest sees every committed schema.
- The cap bounds memory if a team keeps publishing versions; old versions stop being looked up and fall out.
