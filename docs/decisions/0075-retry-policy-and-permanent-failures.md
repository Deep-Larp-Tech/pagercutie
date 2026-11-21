# ADR-0075: Retry policy and permanent failures

- **ID:** ADR-0075
- **Timestamp:** 2026-11-21T06:52+01:00
- **Status:** Accepted
- **See:** `DEL-5`, `DEL-6`, SPEC §10, DOMAIN.md §6, ADR-0074, `backend/src/pagercutie/pipeline/dispatch/stage.py`

## Decision

A failed send is retried without limit. `retry_at` is `now + min(2^attempts, 300)` seconds, where `attempts` counts
the earlier attempts: 1 s, 2 s, 4 s, then 5 minutes at most. Each attempt adds one to `attempts`, increments
`deliveries_total{channel,status="failed"}` and, when a retry is scheduled, `delivery_retries_total{channel}`.

A failure that cannot succeed as configured is permanent: the user has no phone number, the user is deleted or
missing, or the SMTP server answers 5xx. The delivery becomes `failed` with `retry_at` null and is never claimed
again. SMTP 4xx answers and connection errors are transient.

## Rationale

- `DEL-5` says no alert is lost, so a channel that stays down for an hour still delivers when it returns. A cap of N
  attempts would turn a long outage into lost notifications.
- The 5 minute ceiling bounds the delay after recovery and the number of due retries each poll sees.
- Retrying a missing phone number every 5 minutes forever would fill the loop with rows that never succeed, so
  permanent failures are terminal and visible as `failed` with `last_error` in the drawer.
