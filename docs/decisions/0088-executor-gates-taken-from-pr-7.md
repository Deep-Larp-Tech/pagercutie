# ADR-0088: Executor gates, risk defaults and decision validity taken from PR #7

- **ID:** ADR-0088
- **Timestamp:** 2026-11-21T12:00+01:00
- **Status:** Accepted
- **See:** SPEC §5.5, §11.2–§11.4, DOMAIN §6, RUN-4, ADR-0071 (the same defaults in the frontend), PR #7 (ADR-0040 to ADR-0044 on that branch)

## Decision

- The step gates (`Clearance`, `Gate`, `OpenGate`, `FailuresGuard`, `QuestionGuard`, `ApprovalGate`, `ManualGate`,
  `StepGates`), the risk defaults and the status each decision is valid in come from PR #7 (branch
  `feat-action_factory`, ADR-0040 to ADR-0044). Its ADR files are not on `main`, so this ADR carries the decisions.
- Step models stay pure contract models without `run()`. PR #7's ADR-0043 made `runbooks/steps.py` import the
  pipeline, which the import-linter contract "Entity packages do not depend on the pipeline" forbids. The executor
  dispatches actions with an exhaustive `match` on `Step`.
- PR #7's abstract `GateFactory` becomes the function `step_gates(step)`, because there is one implementation.
  Gate order is guard, approval, manual confirmation (`pipeline/executor/gates.py`).
- PR #7's in-memory runner is replaced by the job-table loop (SPEC §11.3). `clearance(status,
  guard_answered, approved)` reads the gates cleared from the flags that the decision endpoint stores on
  `step_runs` (main's decision endpoint, migration 0016); a `running` step has passed every gate. This replaces the
  first version, which derived clearance from the status and the latest decision.
- `requires_approval` is an exhaustive `match`; `approval: required` always applies, `approval: none` never loosens
  a risky default (RUN-4).

| Action | Default approval |
|---|---|
| `http_get`, `wait`, `manual`, `retry_workflow`, `open_ticket` | none |
| `restart_service`, `call_webhook`, `escalate` | required |

## Rationale

- The brief's runbook sets `approval: none` on `retry_workflow`, which is only legal if its default is `none`.
- `call_webhook` can do anything, unlike `http_get`, so it defaults to `required`.
- A function with exhaustive matches gives the same checking as the abstract factory with less structure.
