# ADR-0111: Ingest admission control: an in-flight cap per replica and a token bucket per source

- **ID:** ADR-0111
- **Timestamp:** 2026-11-21T09:04+01:00
- **Status:** Accepted
- **See:** SPEC §5.1, ADR-0042, ADR-0061, ADR-0083, ADR-0110, `backend/src/pagercutie/pipeline/admission.py`,
  `backend/src/pagercutie/core/token_bucket.py`

## Decision

`pipeline/admission.py` holds `Admission`, built once per replica in `create_app` (`app.state.admission`):

- **In-flight cap:** a counter of ingest requests in flight on the replica. Over `ingest_max_in_flight` (default
  32) the request answers `503` with `Retry-After: 1` at once; it never queues.
- **Source rate limit:** a token bucket in Redis under `ingest:{source_slug}:{sha256(Authorization)[:16]}`,
  `ingest_source_burst` tokens (default 1000), refilled at `ingest_source_rate_per_second` (default 500). An empty
  bucket answers `429` with `Retry-After` set to the seconds until the next token. Any `RedisError` lets the event
  through and logs `ingest.rate_limit_unavailable`, as the recipient throttle does.
- Both refusals count in `ingest_refused_total{reason}` (`in_flight`, `rate_limit`).

The webhook route takes the checks as a FastAPI dependency (`INGEST_ADMISSION`), so they run before the body is
read, and lists `429` and `503` in `responses`. The ingest routes are `include_in_schema=False` (ADR-0061), so
`contract/openapi.json` does not change. A WebSocket frame runs `admission.admit` around its processing; a refused
frame gets the existing error frame `{"status": 429 | 503, "detail": …}` and the connection stays open.

The recipient throttle and the source limit share one Lua token bucket in `core/token_bucket.py` (`TokenBuckets`,
key prefix as a parameter); `dispatch/throttle.py` keeps its `throttle:{user_id}` keys.

| Option | Tradeoff |
|---|---|
| **Counter that refuses at once** (chosen) | A full replica answers in microseconds; producers back off with `Retry-After`. |
| `asyncio.Semaphore` that waits | Requests queue in memory and on the pool, which is the latency spiral the review found. |
| Rate limit in Caddy | No per-source key without a plugin, and Caddy cannot see Redis-shared state across its own restarts. |

| Bucket key | Tradeoff |
|---|---|
| **Slug and credential digest** (chosen) | Requests with a wrong token fill their own bucket and get `401` anyway; they cannot use up the real producer's tokens. |
| Slug only | Anyone who knows a slug can make its producer receive `429`. |
| After authentication, inside the handler | Exact per source, but the check would sit in the adapter body after the catalog lookup, and authenticating in the dependency would import the ingest stage outside the orchestrator. |

## Rationale

- ADR-0042 removed the broker, so nothing stood between a burst and the connection pool.
- Defaults: 32 in-flight requests is about twice the request pool (15 connections), because an ingest request holds
  a connection only for its transaction and spends the rest in Redis and evaluation. 500 events/s per source with a
  burst of 1000 is above anything the demo producers send per source and below what one replica handles in total,
  so one noisy source cannot take a replica. Neither number is measured; `docs/load-test-plan.md` says how to tune
  them and to raise the source limit for throughput runs.
- Failing open follows SPEC §5.2: Redis is an accelerator, and dropping events during a Redis outage would lose
  alerts.
