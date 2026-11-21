# ADR-0087: Soft delete rules

- **ID:** ADR-0087
- **Timestamp:** 2026-11-21T14:00+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §3, SPEC.md §8, ADR-0057

## Decision

- `DELETE /rules/{rule_id}` sets `rules.deleted_at`; the row stays and its alerts keep `rule_id`.
- List, get, update and delete treat a deleted rule as missing (`404`), and the rule set leaves it out
  (`rules.service.list_enabled`), so it stops matching after the `rules_changed` reload.
- The column is part of migration 0007; no rule rows existed before the rules API.

| Option | Tradeoff |
|---|---|
| **Soft delete** (chosen) | A rule that fired can be deleted; the row stays, so `DELETE /teams` still answers 409 for a team whose rules were all deleted. |
| Hard delete, 409 while alerts reference the rule | No column; alerts are never deleted, so a rule that ever fired could only be disabled. |
| `alerts.rule_id ON DELETE SET NULL` | Makes `AlertRead.rule_id` nullable, a contract retype (SPEC §4.1). |

## Rationale

- `alerts.rule_id` is `ON DELETE RESTRICT` (ADR-0031), so a hard delete answers 500 once the rule has an alert.
- Users are soft deleted for the same reason (ADR-0057).
- The user chose this option (rules API plan, 2026-11-21).
