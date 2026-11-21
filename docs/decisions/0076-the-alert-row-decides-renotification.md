# ADR-0076: The alert row decides renotification

- **ID:** ADR-0076
- **Timestamp:** 2026-11-21T05:40+01:00
- **Status:** Accepted
- **See:** SPEC §5.2, §9, ADR-0043, ADR-0074

## Decision

- `alerts.notified_at` holds the `received_at` of the event behind the last notification round.
- `dedup.record` is one `INSERT … ON CONFLICT (fingerprint) WHERE status <> 'resolved' DO UPDATE`. It renotifies
  when `notified_at <= received_at - window_s`, whatever the match's Redis claim was. The claim only decides
  whether a match reaches Postgres, and feeds the `dedup_fallback` counter.
- `RETURNING old.notifications` (Postgres 18) is NULL after an insert, so one statement answers `Opened`,
  `Renotified` or `Repeated`.
- Acknowledged alerts renotify like open ones.
- The upsert renders the rule's title, body and fields with the template engine (ADR-0075), and sends
  `NOTIFY alert_changed`. A presentation field that is missing in the event is stored with a `null` value.

Options considered:

| Option | Tradeoff |
|---|---|
| The claim decides (`Won` on an existing alert renotifies) | No extra column. A `Pending` match that inserts first makes the winner renotify milliseconds later; a Redis outage stops renotification; a Redis restart renotifies every open alert. |
| **The row decides through `notified_at`** (chosen) | One more column. Racing matches meet on one row and the second repeats; renotification works without Redis. |

## Rationale

- The user accepted the change after the race was traced: the fix stored the alert ID for a fallback's `Opened`,
  but the winner is already inside its transaction by then.
- It applies ADR-0043's rule, Redis accelerates and Postgres decides, to renotification as well.
