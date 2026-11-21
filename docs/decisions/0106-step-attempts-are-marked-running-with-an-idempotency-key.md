# ADR-0106: Step attempts are marked `running` with an idempotency key; unfinished claims are bounded

- **ID:** ADR-0106
- **Timestamp:** 2026-11-21T18:05+01:00
- **Status:** Accepted, amends ADR-0008 for step runs
- **See:** SPEC §11.2, §11.3, migration 0021, `backend/src/pagercutie/pipeline/executor/claims.py`

## Decision

- Before an action runs through an integration (`http_get`, `call_webhook`, `retry_workflow`, `restart_service`,
  `open_ticket`), `start_step` commits `status = running`, a new `attempt_key` (UUIDv7) and `acted_at`, conditional on
  the claim's lease, and audits `step.started`. The action sends the key: the `Idempotency-Key` header for HTTP, an
  argument for `OpsService`. `SimulatedOps` remembers each key's result and answers a repeated key without acting.
- A step claimed while `running` lost the replica that ran it. It runs again with the same key and `acted_at`, and is
  not audited as started again.
- A claim that finds `lease_until` set knows the previous claim ended without an outcome (an exception or a lost
  replica) and adds one to `errors`. At `executor_step_max_errors` (default 5) the step fails with "Gave up after N
  attempts", one more `failures` and an audit entry with `"reason": "errors"`, and the run moves on.

| Option for a step found `running` with an expired lease | Tradeoff |
|---|---|
| **Run again with the same key** (chosen) | The run makes progress; an integration that honours the key acts once. A webhook that ignores `Idempotency-Key` may receive the request twice |
| Fail it as "outcome unknown" | Never repeats a side effect, but every lost replica fails a step, which feeds `FailuresGuard` and can trigger an escalation nobody needed |

| Option for counting errors | Tradeoff |
|---|---|
| **Count at the claim, from a lease left behind** (chosen) | One mechanism covers exceptions and lost replicas, and the count is written even when the database was what failed |
| Count in the worker's `except` branch | Faster retry after an exception, but a lost replica is never counted and a database outage loses the count |

## Rationale

- A crash between the action and `complete_step` used to repeat a restart or webhook POST after 30 s with nothing
  recording that it had run; `running` plus the key make the repeat visible and, for integrations that honour the
  key, harmless.
- The bound: 5 claims at the 30 s lease fail a poisoned step about 2.5 minutes after its first attempt, which rides
  out a short database or network outage while stopping a step that raises on every attempt.
- `acted_at` also lets a watched retry ignore occurrences received before its attempt started (SPEC §11.4).
