# ADR-0040: Action factory over the `Step` union, and an in-memory runbook run

- **ID:** ADR-0040
- **Timestamp:** 2026-11-20T22:03+01:00
- **Status:** Accepted, amended by ADR-0042 and ADR-0043
- **See:** SPEC §11.2, §11.3; ADR-0019

## Decision

- Parsers turn every runbook format into `list[Step]`. The abstract `ActionFactory` (now `StepFactory`, ADR-0042)
  (`backend/src/pagercutie/runbooks/factory.py`) has one abstract method per step type. Its `create(step)`
  dispatches to them with an exhaustive `match` ending in `assert_never`. How each action is performed is left to
  concrete factories and `Action` subclasses.
- `Action.run()` is abstract and returns an `ActionResult` (`ok`, `summary`, `outputs`). Expected failures are a
  result with `ok=False`, not an exception. The factory receives steps whose values are already in final form, so
  actions do no template rendering.
- `RunbookRun` (`runbooks/run.py`) is the per-alert state machine, kept pure and in memory. The service will load
  it from Postgres and save it back. It applies each result to the step's state (status, attempts, failures,
  result, outputs) and keeps the list of transitions with who made them, for the audit log.
- Approval defaults live in the state machine (`requires_approval`, exhaustive over `Step`), not in actions, so an
  implementation cannot loosen them (`RUN-4`). Defaults that SPEC left open: `call_webhook` is `required` (it can
  do anything), `retry_workflow` and `open_ticket` are `none` (the brief sets `approval: none` on the retry, and
  that may only be stricter than the default).
- Gates are checked in the order guard → approval → manual. A structured guard that is still false leaves the step
  `pending` and the run waits there. A failed step does not stop the run, because later steps may be guarded on its
  failures.

## Rationale

- A string-keyed registry would let a new step type compile without a handler. One abstract method per step type
  plus the `match` makes `ty check` fail instead (SPEC §4.4). This was verified by deleting a case.
- A pure state machine can be tested with a recording factory and no database, and maps directly onto the planned
  job-table executor.

## Known limits

- No concrete actions exist yet: integrations (HTTP, the mock service, escalation) are the next step.
- `{{field}}` placeholders (SPEC §11.2) are not rendered anywhere yet; whatever builds the steps for the factory
  must fill them in first.
- Running the retry again after a repeat occurrence (SPEC §11.4) and closing the alert automatically (`RUN-5`) are
  not implemented yet.
