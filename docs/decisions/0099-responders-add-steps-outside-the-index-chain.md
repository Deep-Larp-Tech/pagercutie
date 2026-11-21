# ADR-0099: Responders add steps to a runbook run; added steps run outside the index chain

- **ID:** ADR-0099
- **Timestamp:** 2026-11-21T16:00+01:00
- **Status:** Accepted
- **See:** REQUIREMENTS `RUN-7`, SPEC §11.3, DOMAIN.md §3, §6, §7, ADR-0088, ADR-0095, `alerts/service.py`
  (`add_step`), `pipeline/executor/stage.py` (`_advance`, `_has_unfinished_step`)

## Decision

- `POST /alerts/{alert_id}/runbook-run/steps {step: AddedStep}` appends a step to the alert's run (`RUN-7`: record
  what was done to resolve an incident). `AddedStep` is the `Step` union without `wait`; an `if` guard answers 422.
  Same roles as acknowledge; 409 once the alert is resolved, 404 when it has no run. Answers 201 with the run.
- A `manual` step records something the responder already did: stored `succeeded`, decided by them. Any other action
  is `pending` and due at once, and passes the executor's gates like a runbook step, so a risky one waits for a lead.
- `step_runs.added_by` names who added the step (null for steps copied from the runbook) and is on `StepRunRead`.
  The alert's row lock serialises adds with each other and with `close_run`, so indexes stay contiguous (max + 1).
  Each add is audited as `step.added`.
- **Added steps run outside the index chain.** `_advance` and `schedule_next_step` make only the next pending
  *runbook* step due, and `_has_unfinished_step` (which keeps a succeeded retry watching) ignores added steps. A
  claimed step stays `pending` with its lease in `run_at`; making an added step "next" would move `run_at`, drop its
  outcome as stale and run its action twice. Replicas still on the previous version keep that race until the
  rolling update completes.
- `runbook_run.finished` can be audited again when a finished run gets an added step that then finishes.
- `ResolveRequest.note` is stored as `alerts.resolution_note` and returned on `AlertRead` (additive), so "what fixed
  it" is typed data instead of only audit `data`.

| Option for scheduling | Tradeoff |
|---|---|
| **Filter on `added_by IS NULL`** (chosen) | The runbook chain behaves exactly as before; added steps are scheduled once, when added. |
| Only schedule a step whose `run_at` is null | Skips a leased runbook step and runs the one after it out of order, or loses the wake-up a failed retry gives a guarded step. |

## Rationale

- Work done outside the runbook is the input for runbook suggestions (`RUN-7`); recording it as typed steps keeps
  `step_runs` the single record of what was done and by whom (`RUN-5`).
