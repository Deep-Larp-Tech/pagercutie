# ADR-0077: Resolving an alert deletes its dedup window

- **ID:** ADR-0077
- **Timestamp:** 2026-11-21T06:00+01:00
- **Status:** Superseded by ADR-0101 (a resolved marker and the delete run before the commit)
- **See:** SPEC §5.2, DOMAIN.md §6, ADR-0074

## Decision

- After a resolve commits, manual or automatic (`RUN-5`), the service calls `core.redis.delete_dedup_window`,
  which deletes `dedup:{rule_id}:{fingerprint}`. The next match then claims a new window and opens a new alert.
- The key format lives in `core.redis.dedup_window_key`; the dedup stage's `window_key` uses it, because entity
  packages may not import `pipeline`.
- An unreachable Redis is logged and ignored: the alert stays resolved and the old window expires within
  `window_s`.
- `alerts` resolve still answers `501`; whoever implements it calls the helper.

Options considered:

| Option | Tradeoff |
|---|---|
| Leave the window | No code. A recurrence counts on the resolved alert, unseen, for up to `window_s` (24 h at most). |
| **Resolve deletes the key** (chosen) | One Redis call after the commit; a recurrence opens a new alert at once. |
| Delete from a `NOTIFY alert_changed` listener | Covers every code path that resolves, but adds a listener and a delay. |

## Rationale

- The user chose deleting the key on resolve.
