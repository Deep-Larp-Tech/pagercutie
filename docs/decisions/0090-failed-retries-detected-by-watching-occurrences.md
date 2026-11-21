# ADR-0090: Failed retries are detected by watching occurrences

- **ID:** ADR-0090
- **Timestamp:** 2026-11-21T13:00+01:00
- **Status:** Accepted, amended by ADR-0093 (resolving an alert ends the watch)
- **See:** SPEC §5.2, §11.3, §11.4, ADR-0020, ADR-0088, docs/plans/runbook-executor.md D4

## Decision

A succeeded `retry_workflow` step stores the alert's `occurrences` as `step_runs.occurrences_at_run` and stays
claimable with `run_at = now + 5 s` (`WATCH_INTERVAL`). Each claim compares the alert's current count with the
baseline:

- Equal: `RetryWatched`, checked again 5 s later. Watching ends (`run_at` null) once every step of the run is
  finished; the claim query already parks the steps of resolved alerts.
- Higher: `RetryFailed`. The retry runs again (`attempts + 1`), the current count becomes the baseline and
  `failures` goes up by 1 (audit action `step.retry_failed`, added to the typed audit log by migration 0019; it names the alert). If the re-run fails too, the step becomes `failed` and
  `failures` goes up by 2: the watched attempt and the re-run both failed.

A counted failure schedules the run's next pending step, so a guard such as `retry fails twice` is checked again.
Re-runs skip the gates: an approval given for the step covers its re-runs.

| Option | Tradeoff |
|---|---|
| Poll `alerts.occurrences` against a baseline (chosen) | Sees every repeat, including `Held` ones that dedup counts in Redis and flushes later (ADR-0078). Detection lags by up to 5 s plus the flush delay; adds one claim per watched retry every 5 s |
| Orchestrator calls the executor on `Repeated` / `Renotified` | Immediate, but misses `Held` repeats, which open no transaction, so "fails twice" may never trigger |

## Rationale

- The count in `alerts.occurrences` is the one place every repeat ends up, so a baseline comparison needs no
  change to the pipeline stages, which must not import each other (SPEC §5.5).
- 5 s is short against retry times measured in minutes and adds one indexed claim per watched retry.
- Counting 2 failures for a failed re-run keeps the guard threshold meaning "failed attempts", not "detections".
