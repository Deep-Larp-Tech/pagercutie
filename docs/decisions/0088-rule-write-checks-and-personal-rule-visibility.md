# ADR-0088: Rule write checks and personal-rule visibility

- **ID:** ADR-0088
- **Timestamp:** 2026-11-21T14:05+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §4, SPEC.md §8, ADR-0026

## Decision

**Who may do what:**

| Action | Team rule | Personal rule |
|---|---|---|
| See (list, get) | Any role in the team, or `admin` | The owner, or `admin` |
| Create, edit, delete | `member`, `lead`, or `admin` | The owner only; `admin` answers 403 |

A rule the user cannot see answers 404; one they can see but not change answers 403. Lists are ordered by `id`.

**Checks on create and update** run before anything is written. On `PATCH` only the fields in the body are checked.
Each problem is one `{loc, msg}` entry of a single `422`:

| Field | Check |
|---|---|
| `owner` | A team owner the user cannot edit answers 403, an unknown team 404 (as `POST /sources`); a user owner other than the current user answers 403 |
| `schema_ids` | Every ID is an existing event schema, listed once |
| `routing.recipients` | A personal rule notifies only `{"type": "user", "user_id": <owner>}`; a team rule's `user` recipients are active users and `team` / `on_call` recipients existing teams, of any team |
| `runbook_id` | A team rule's runbook belongs to its team; a personal rule's to a team its owner can see (any team for an admin) |
| `condition` | No text value contains NUL |

## Rationale

- DOMAIN §4 gives personal-rule writes to "the owning user only" and admins "everything", so admins read
  personal rules but do not change them.
- ADR-0026 says a personal rule notifies only its user; the routing check enforces it.
- A runbook from another team would make the rule team's leads approve risky steps in a runbook they do not own
  (`RUN-1`: teams attach their runbooks).
- `load_rule_set` adds a rule once per `schema_ids` entry, so a repeated ID would evaluate the rule twice per event.
- Postgres `jsonb` cannot store `\u0000`, so a NUL in a condition would answer 500. The check lives in the
  service, not the AST: `/rules/test`, the contract and the evaluator property test stay unchanged.
- A field `loc` lets the rule builder mark the field (`UI-6`).
