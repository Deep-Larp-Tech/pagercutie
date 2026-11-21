# ADR-0079: Typed audit actions and entity types; every change writes an entry

- **ID:** ADR-0079
- **Timestamp:** 2026-11-21T06:35+01:00
- **Status:** Accepted
- **See:** SPEC §4.1, §12.1, DOMAIN.md §3, §7, ADR-0031, ADR-0057, ADR-0065

## Decision

- `AuditEntry.action` and `entity_type` are the enums `AuditAction` and `AuditEntityType` (`audit/schemas.py`),
  stored as the Postgres enums `audit_action` and `audit_entity_type` (migration 0013, ADR-0031). The entity type
  follows from the action (`entity_type_of`, an exhaustive `match`), so a writer cannot pair them wrongly.
- `AuditEntryRead.action` and `entity_type` change from `string` to those enums, and so does the `entity_type`
  query parameter. This breaks the additive rule of SPEC §4.1; accepted because nothing wrote audit entries before
  and no client outside this repository uses the API yet. An unknown `entity_type` now answers 422 instead of an
  empty list.
- `AuditAction` also holds the actions that routes and loops still answering 501 must write (alert acknowledge,
  resolve, escalate; step transitions and decisions; rule and runbook changes), so they need no `ADD VALUE`
  migration when they land. `step.*` entries name the alert.
- `GET /audit` gains `actor_user_id`, `system` (actor is the system), `action` (repeatable, any of), `since`
  (inclusive), `until` (exclusive) and `without_team`. `system` with `actor_user_id`, `without_team` with
  `team_id`, and `since` at or after `until` answer 422. Indexes `(actor_user_id, at)` and `(action, at)` back the
  new filters.
- `AuditEntryRead` gains `actor_name` (additive): the actor's `display_name` through an outer join on `users`, kept
  after a soft delete (ADR-0057), null for the system.
- Services write entries with `audit.service.record` in the request's transaction. Implemented today: users
  (create, update, delete, channel preferences), the admin bootstrap (as the system), teams (create, update,
  delete, member added / role changed / removed, channel preferences, rotation), sources (create, update, delete,
  token rotation), event schema versions (create), and the dedup stage (alert opened, alert renotified, as the
  system).
- `data` holds the changed fields as `{"before", "after"}` for an update, and the identifying fields for a create or
  delete. It never holds an ingest token or its hash. An update that changes nothing writes no entry.
- Not audited: login and logout, and dedup repeats (one per matching event inside the window).

Options considered for the vocabulary:

| Option | Tradeoff |
|---|---|
| **Backend enums** (chosen) | One source of truth, generated TS unions, exhaustive checks on both sides. Retypes contract fields; every new action is an `ADD VALUE` migration. |
| Frontend-only list, contract stays `string` | No backend change; two hand-kept lists that drift as writers land. |
| `GET /audit/facets` listing stored values | Additive; values stay `string`, and an extra query per page load. |

Options considered for filtering on null columns:

| Option | Tradeoff |
|---|---|
| **Boolean flags `system`, `without_team`** (chosen) | Plain typed params; one rule rejects the contradicting pair. |
| A sentinel value (`actor=system`) | One param, but a `uuid \| "system"` union the generated client types as `string`. |

## Rationale

- The user chose backend enums so the audit log UI can offer dropdowns that the type checker keeps complete.
- Writing the entry in the same transaction as the change means a rolled-back change leaves no entry (SPEC §12.1).
- A server-side join gives every page its actor names in one request, without the client paging `GET /users`.
