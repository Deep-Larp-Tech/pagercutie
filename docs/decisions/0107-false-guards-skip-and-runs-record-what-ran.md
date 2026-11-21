# ADR-0107: A false structured guard skips its step; runs record what ran

- **ID:** ADR-0107
- **Timestamp:** 2026-11-21T18:10+01:00
- **Status:** Accepted, amends ADR-0095 (a step in flight keeps running through the resolve)
- **See:** SPEC §11.3, §11.4, RUN-5, ADR-0020, ADR-0090

## Decision

- The user decided that a structured guard (`FailuresGuard`) that is false skips its step and the run goes on. The
  guard is false only when the guarded step can no longer fail: it is final and is not a succeeded `retry_workflow`
  (which is watched while the run has an unfinished step). The step becomes `skipped` with the guard in `result` and
  `step.skipped` audited with `"reason": "guard_false"`, distinct from `"reason": "resolved"`.
- While the guarded step can still fail, the guard's answer is not known: the step stays `pending` with `run_at` null
  (`GuardPending`) and is checked again when that step counts a failure. Unparsed guards still wait for a person
  (`awaiting_answer`).
- Resolving an alert leaves a `running` step whose lease is live alone: its action is in flight. The executor writes
  the real outcome and finishes the run. If that replica is lost, the claim's park path fails the step with "Outcome
  unknown" (a `wait` is skipped) and finishes the run.
- An outcome dropped as stale is audited when its action ran (`step.succeeded` or `step.failed` with `"discarded":
  true` and the attempt key); other stale outcomes are only logged.

## Rationale

- With steps `[A, B if "A fails twice", C]` and A succeeding, C never ran and the run never finished; skipping B lets
  the run end and be audited.
- Treating a watched retry's guard as false would skip the brief's escalation as soon as the retry succeeded once.
- RUN-5 asks for what was done: marking an executing restart `skipped` on resolve, or dropping its late outcome
  silently, recorded something other than what happened. Audit entries with `"discarded": true` avoid a new
  `AuditAction` value, so the HTTP contract and the Postgres enum stay unchanged.
