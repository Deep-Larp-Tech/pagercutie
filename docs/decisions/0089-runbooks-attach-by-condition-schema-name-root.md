# ADR-0089: Runbooks attach by condition; the event view gains the schema name

- **ID:** ADR-0089
- **Timestamp:** 2026-11-21T13:00+01:00
- **Status:** Accepted
- **See:** SPEC §4.2, §4.3, §11.1, ADR-0062, ADR-0065, `RUN-1`, docs/plans/runbook-executor.md D8

## Decision

- `start_run` uses the rule's `runbook_id` when set, even if that runbook no longer exists (then no run starts).
- With no link, it picks the oldest runbook (`created_at`, then `id`) whose compiled `attach` condition is true for
  the run's event view, among runbooks of the alert's team (`Alert.team_id`, the team that owns the rule). A
  personal rule has no team and only uses its link.
- The event view gains a fifth root, `schema`: the event schema's `name`, `null` when unknown. `Event` carries it
  as `schema_name` (a field named `schema` would shadow `BaseModel.schema`); ingest sets it from the winning schema.
- Alert types need no new root: they are payload conditions (`payload.type = WORKFLOW_FAILED`).
- Rule-test fixtures gain an optional `event.schema`; a case without it means unknown.

Options for attaching to schemas:

| Option | Tradeoff |
|---|---|
| **`schema` root with the schema name (chosen)** | Survives version bumps, readable in YAML, usable by rules. Touches the rule contract: a fifth root and new cases. |
| `schema_ids` column on runbooks | Explicit and indexable; a second way to say "when", tied to version IDs unless it stores names. |
| Match through a payload field every schema carries | No work; depends on the producer. |

Breaking edge: roots win over payload keys (ADR-0062), so a bare `schema` path no longer reads `payload.schema`.
Use `payload.schema` for the payload key.

## Rationale

- Candidates come from the alert's team because that team handles the alert, and schema names are unique only per
  team. The source's team can differ from the rule's team.
- Oldest first is predictable, and `runbook_runs.alert_id` allows one run per alert. Rejecting overlapping `attach`
  conditions at save time is undecidable for the AST in general.
- The evaluator's compiled predicates run against the same view the run stores, so `attach` and step templates
  see one event.
- No cache: one query per opened alert over one team's runbooks, which are few.
