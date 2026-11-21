# ADR-0081: Throttled deliveries merge into a digest delivery row

- **ID:** ADR-0081
- **Timestamp:** 2026-11-21T06:50+01:00
- **Status:** Accepted
- **See:** SPEC §9 and §10, DOMAIN.md §6, ADR-0083, `backend/src/pagercutie/pipeline/dispatch/stage.py`

## Decision

A delivery that finds its recipient's token bucket empty stays `pending` with `retry_at` at the next token, and
`merge_into_digest` folds it into a digest. The digest is an ordinary delivery row for the same user and channel;
`deliveries.digest_id` (nullable, FK to `deliveries.id`) points each member at it.

- Members stay `pending` and are skipped by `claim_due` while `digest_id` is set. The digest is claimed, throttled
  and sent like any delivery and carries the oldest member's `alert_id` and `received_at`.
- A new digest needs two candidates (`pending`, not leased, not already in a digest, not a digest). Its ID is a UUIDv5
  of its first members' IDs, so repeating a merge inserts one row. Later throttled deliveries of the same user and
  channel join the open digest (a `pending` digest no dispatcher holds) and rewrite its message.
- Merges per user and channel run one at a time under `pg_advisory_xact_lock`, so a burst completing concurrently
  ends in one digest, not several.
- When the digest is `sent`, its members become `sent` with the same `sent_at`. When it fails permanently
  (ADR-0082), its members become `failed` with no `retry_at`. A transient failure retries the digest and leaves
  the members `pending`.
- The digest message is a count line plus the first line of up to 10 member messages, then `... and N more`.

## Rationale

- One table and one loop. `DEL-6` status stays per recipient and channel, and the drawer lists members and digest
  with the existing `GET /deliveries`.
- A separate `digests` table would add a table and a second claim loop for no extra behaviour. Delaying throttled
  deliveries without a digest breaks SPEC §9 ("grouped into a digest instead of being dropped") and still sends one
  message per delivery once the bucket refills.
- The advisory lock serialises only deliveries of one recipient and channel, so unrelated merges do not wait.
- A cap of 10 lines keeps an SMS digest short; the count line states how many were held back.
