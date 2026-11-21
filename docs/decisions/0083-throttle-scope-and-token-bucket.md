# ADR-0083: Throttle scope and token bucket

- **ID:** ADR-0083
- **Timestamp:** 2026-11-21T06:54+01:00
- **Status:** Accepted
- **See:** SPEC §5.2 and §9, ADR-0081, `backend/src/pagercutie/pipeline/dispatch/throttle.py`

## Decision

Only email, SMS and phone deliveries take a token. UI deliveries skip the throttle.

The bucket is one per user, not per channel, in Redis under `throttle:{user_id}`. It holds `throttle_capacity` tokens
(default 5) and gains one every `throttle_refill_seconds` (default 12). A Lua script reads Redis's own clock, so
replicas with skewed clocks share one bucket, and sets a key expiry at the time the bucket is full again. An
empty bucket makes `send` return `Throttled` and the delivery joins a digest (ADR-0081).

The throttle fails open: any `RedisError` is logged as `dispatch.throttle_unavailable` and the delivery is sent. The
Redis client has a 0.5 s connect and socket timeout, so an unreachable Redis costs a send at most that long.

## Rationale

- The UI channel is a feed row. Throttling it would hide alerts from the live feed (`UI-1`) without protecting
  anyone's phone.
- One bucket per user caps the total interruptions a person gets, whichever channels the preferences pick.
- Failing open follows SPEC §5.2: a duplicate or extra message during a Redis outage is cheaper than a missed
  page.
- The 0.5 s timeout keeps a dead Redis from stalling the sends that wait behind it.
