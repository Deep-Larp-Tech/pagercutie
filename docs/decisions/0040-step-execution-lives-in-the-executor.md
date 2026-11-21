# ADR-0040: Step interpretation and execution live in the executor package

- **ID:** ADR-0040
- **Timestamp:** 2026-11-21T14:30+01:00
- **Status:** Accepted
- **See:** SPEC §3.2, §11.2, §11.3; ADR-0030, ADR-0037, ADR-0038, ADR-0039

## Decision

- `interpreter.py`, `actions.py`, `gates.py`, `factory.py` and `run.py` move from `backend/src/pagercutie/runbooks/`
  to `backend/src/pagercutie/pipeline/executor/`, next to the executor role's `worker.py`. Paths in ADR-0030 and
  ADR-0037 to ADR-0039 refer to the old location.
- `runbooks/steps.py` stays in `runbooks/`: it is the runbook contract model (`contract/runbook.schema.json`) that
  `runbooks/schemas.py`, `runbooks/models.py` and `alerts/` import. It imports `Action` and `ActionContext` from
  `pipeline.executor.actions`, which imports nothing from `runbooks`, so there is no import cycle.

## Rationale

- The executor role (SPEC §3.2) is the code that interprets and runs steps; keeping that code in its package
  separates it from the runbook entity's `router → service → models`.
- Moving `steps.py` would make the entity modules and the API contract depend on the pipeline package.
