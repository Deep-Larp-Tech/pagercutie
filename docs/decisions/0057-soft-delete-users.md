# ADR-0057: Soft delete users

- **ID:** ADR-0057
- **Timestamp:** 2026-11-20T23:33+01:00
- **Status:** Accepted
- **Decided by:** TechPriest
- **See:** DOMAIN.md §3, §4, ADR-0031

## Decision

- Deleting a user sets `users.deleted_at`; the row stays.
- List, get and update hide soft-deleted users and answer `404`. Deleting a soft-deleted user again answers `404`.
- Deleting a user removes their sessions, and login is refused for them.
- Team memberships and rotation slots are kept.
- Email is unique among active users only (partial unique index on `email WHERE deleted_at IS NULL`), so an email
  can be reused after its user is deleted.
- Only `admin` deletes users.

## Rationale

- A hard delete fails for any user with history: `alerts.acknowledged_by`, `alerts.resolved_by`,
  `deliveries.user_id`, `rules.user_id` and `step_runs.decided_by` are `ON DELETE RESTRICT` (ADR-0031).
- `audit_log.actor_user_id` has no foreign key, so history outlives users either way.
- A hard delete with `SET NULL` or cascades would lose who acknowledged, resolved or decided what.
