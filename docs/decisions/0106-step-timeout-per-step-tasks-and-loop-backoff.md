# ADR-0106: Step timeout inside the lease, one task per step, loop backoff and step spans

- **ID:** ADR-0106
- **Timestamp:** 2026-11-21T18:20+01:00
- **Status:** Accepted
- **See:** SPEC §11.3, §13, ADR-0008, ADR-0107, `backend/src/pagercutie/pipeline/executor/worker.py`

## Decision

- Each action runs under `executor_step_timeout_seconds` (default 20 s). A timeout is the typed outcome
  `StepTimedOut`, written as `failed` with `"reason": "timed_out"`. `Settings` rejects a timeout that, with
  `db_worker_pool_timeout_seconds`, reaches `executor_lease_seconds` (default 30 s), so the outcome is written before
  another replica may claim the step.
- The loop runs each claimed step as its own task, holds at most 20 in flight and claims only free slots; it wakes on
  `steps_pending`, when a task ends and every second. Stopping waits for the tasks in flight.
- After a failed pass the loop waits 2, 4, 8, 16, then 30 s between passes, and resets after a good pass.
- Each step opens a root span `executor.step` linked to the trace context stored on the step run by `start_run`
  (`step_runs.traceparent`), as dispatch does for deliveries.

## Rationale

- `OpsService` had no timeout and `asyncio.gather` held the next claim until the slowest step of the batch ended; a
  step that outlived its lease could run on two replicas.
- One log line a second during a database outage buried the first error.
