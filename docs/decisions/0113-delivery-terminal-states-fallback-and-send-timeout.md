# ADR-0113: Delivery terminal states, channel fallback, send timeout inside the lease

- **ID:** ADR-0113
- **Timestamp:** 2026-11-21T09:06+01:00
- **Status:** Accepted
- **Amends:** ADR-0081 (digest membership), ADR-0082 (permanent failures)
- **See:** `DEL-5`, `DEL-6`, SPEC §10, DOMAIN.md §6, ADR-0027, `backend/src/pagercutie/pipeline/dispatch/`,
  migration `0022`

## Decision

**Terminal states.** `DeliveryStatus` gains `undeliverable` (failed permanently, never retried) and `cancelled`
(its alert was resolved before it was sent). `failed` now always means "another attempt is scheduled". Migration
`0022` adds both values and moves existing `failed` rows without `retry_at` to `undeliverable`.
`dispatch/state.py` parses a row's `status`, `retry_at`, `lease_until` and `digest_id` into one union
(`Due | HeldBack | InDigest | Leased | Retrying | Delivered | Undeliverable | Cancelled`) and holds the SQL
predicates (`due`, `unsent`) next to the parser.

**Resolved alerts.** Each dispatch pass first runs `cancel_for_resolved_alerts`: up to one batch of unsent,
unleased deliveries (pending, held back, digest members, retrying) whose alert is `resolved` become `cancelled`
with `last_error` "Alert resolved before the delivery was sent", under `FOR UPDATE SKIP LOCKED OF deliveries`. A
digest is never cancelled through its own `alert_id` (the oldest member's); `claim_due` cancels a digest that has
no `pending` member left. Acknowledged alerts keep sending and retrying: SPEC §5.2 says they renotify, and SPEC
§10 says nothing about stopping their retries.

**Fallback.** A permanent failure marks the delivery (or each member the digest listed) `undeliverable`, then
`dispatch/fallback.py` inserts a `pending` delivery on the recipient's next untried channel, in the completion's
transaction, with `NOTIFY deliveries_pending`:

- Order: `preferences.resolution.fallback_channels`: the channels of every one of the user's own preference rules
  matching the alert's severity, in rule order and ignoring windows, then email. UI is never a fallback.
- Tried: channels of the alert's deliveries to the user with the same `received_at`, which every delivery of one
  notification round shares (routing, digest members and fallbacks carry it over).
- ID: UUIDv5 of the failed delivery's ID and the channel, so a repeated completion inserts nothing.
- Nothing left, or the user is deleted: `recipients_unreachable_total{channel}` and a `dispatch.unreachable`
  warning; the alert's deliveries in `GET /deliveries` are all `undeliverable`.

| Where the channel order comes from | Tradeoff |
|---|---|
| **Shared function in `preferences/resolution.py`** (chosen) | Entity module, importable by dispatch; next to `resolve_channels`, which routing uses. Does not know whether routing used the team's preferences. |
| Import routing's selection | Stages may not import each other (SPEC §5.5). |
| Routing stores the whole fallback chain on each delivery | Exact, but a new column, a routing change (another owner) and a chain frozen at routing time. |
| Fixed channel order (phone, SMS, email) | Ignores the preferences ADR-0027 defines. |

**Send timeout.** `dispatch.send` wraps the adapter in `asyncio.timeout(delivery_send_timeout_seconds)` (default
15 s); a timeout is a transient `SendFailed`. A settings validator requires
`delivery_send_timeout_seconds + db_worker_pool_timeout_seconds + 5 s ≤ delivery_lease_seconds`, so a send and its
completion end before another replica may claim the row. SMTP's 10 s per reply stays inside it.

**Digest members.** `claim_due` composes a claimed digest's message from the members it carries at that moment and
puts their IDs in the job (`Digest(member_ids)`). Completion marks only those members `sent` or `undeliverable` and
detaches any later `pending` member (`digest_id = NULL`) so it is sent on its own. `merge_into_digest` joins an open
digest only when its `lease_until` is null, never one whose lease expired mid-send.

**Metrics.** `complete` returns a `Completion` (`Delivered | RetryScheduled | GaveUp | Postponed | LeaseLost`) and
`dispatch/metrics.py` records it; no SQL writer records metrics. New counters: `deliveries_throttled_total`,
`digests_created_total`, `deliveries_cancelled_total`, `delivery_fallbacks_total{from_channel,to_channel}`,
`recipients_unreachable_total`, `delivery_leases_lost_total`. `deliveries_total{status}` gains `undeliverable`.

**Dispatch loop errors** back off 1, 2, 4 … 30 s instead of retrying every second.

## Rationale

- `DEL-5`: a resolved alert kept paging through unlimited retries, and an on-call user without a phone number got
  nothing at all, silently.
- An explicit status lets the drawer tell "retrying" from "gave up" and "cancelled"; `retry_at` was doing that job.
- Fallback by notification round, not by alert, lets a renotification try the preferred channel again.
- Email last: every user has an address, and it is the only channel that reaches a user with no phone number.
- The audit entry the review asked for needs an `audit_action` enum value, which is a migration outside the
  deliveries table; it is left for a separate change.
