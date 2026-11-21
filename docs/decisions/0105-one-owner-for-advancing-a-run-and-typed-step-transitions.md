# ADR-0105: One owner for advancing a run, a separate lease column and typed step transitions

- **ID:** ADR-0105
- **Timestamp:** 2026-11-21T18:15+01:00
- **Status:** Accepted
- **See:** SPEC §11.3, migration 0021, `backend/src/pagercutie/alerts/runs.py`,
  `backend/src/pagercutie/pipeline/executor/transitions.py`

## Decision

- `alerts/runs.py` owns how a run moves on: `is_final` (an exhaustive `match`; `FINAL_STEP_STATUSES` derives from it),
  `lock_run`, `advance_run` and `finish_run`. The decision endpoint and the executor both call `advance_run`; the
  alerts package may not import the pipeline, so it lives there. The next step is the first `pending` step with a
  higher index, and its `run_at` becomes now.
- `step_runs.lease_until` holds the claim's lease; `run_at` means only when the executor looks at the step next. A
  claim requires an expired lease and the outcome `UPDATE` is conditional on `lease_until`, so making a leased step
  due never lets a second replica run it. A leased step whose claim ends in `GuardPending` keeps a `run_at` written
  after its claim, so a failure counted during its guard check is not lost.
- `runbook_runs.finished_at` records the run's end. `finish_run` sets it with a conditional `UPDATE`, so
  `runbook_run.finished` is audited exactly once. Every writer takes locks in the order alert, run, steps: the
  resolve locks the alert first, and an escalating `complete_step` locks the alert before the run.
- The executor maps each outcome to a `Transition = Finish | Await | Hold | Delay | Watch` (frozen dataclasses,
  matched with `assert_never`) in a pure module, and `completion.py` writes it. `executor/stage.py` re-exports the
  entrypoints from `runs`, `claims`, `perform`, `transitions` and `completion`.
- Removed: `Clearance.done` and `ManualGate` (the decision endpoint marks a manual step `succeeded`, so the executor
  only sees it unticked), the `clearance()` special case for `running`. `QuestionGuard` now yields
  `AwaitingAnswer(question)` itself.

## What stays weak

- The step row is still `status` plus the flags `guard_answered` and `approved`, and `occurrences_at_run` doubles as
  "this retry is watched". Replacing them with a per-status column set needs a data migration of every step run and
  of the decision endpoint's contract (DOMAIN §6); this ADR does not attempt it.
- The run has no status column: SPEC §11.3 describes only step states, and `finished_at` is the one run fact the code
  needs.

## Rationale

- Two "next step" policies (index + 1 in the decision endpoint, next pending in the executor) disagreed when a step
  in between was already final; the decision endpoint also never audited `runbook_run.finished`.
- Overloading `run_at` as schedule and lease let a schedule write break a live lease (a second replica ran the step
  again).
