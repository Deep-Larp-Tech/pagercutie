# ADR-0109: A failed send gives its throttle token back

- **ID:** ADR-0109
- **Timestamp:** 2026-11-21T09:05+01:00
- **Status:** Accepted
- **See:** SPEC §9, §10, ADR-0083, `backend/src/pagercutie/pipeline/dispatch/stage.py`,
  `backend/src/pagercutie/core/token_bucket.py`

## Decision

The user decided: a send that took a token from the recipient's bucket and ended in `SendFailed` (returned, raised
or timed out) gives the token back. Critical severity stays throttled, and ADR-0083's per-user limit is unchanged.

`Throttle` gains `refund(user_id)`. `dispatch.send` calls it after a failed send that took a token; a `Throttled`
result and the UI channel took none and refund nothing. `RedisThrottle.refund` runs the `REFUND` Lua script in
`core/token_bucket.py`: it applies the refill since the last call, adds one token capped at `capacity`, and leaves a
missing key (a full bucket) alone. It fails open: a `RedisError` is logged as `dispatch.throttle_unavailable`.

## Rationale

- Without the refund an SMTP outage drains every recipient's bucket on retries, and the next real page waits behind
  a digest even though nothing reached the person.
- One Lua script keeps the read, refill and write atomic across replicas, like the take.
- A refund after a fail-open take (Redis was down when the token should have been taken) adds a token that was never
  taken. The capacity cap bounds this to a full bucket, which is the state an idle user has anyway.
