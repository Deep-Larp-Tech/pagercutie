# Runbook executor implementation plan

Status: draft for review. Sources: SPEC §5.3–§5.5, §11; DOMAIN §4, §6; REQUIREMENTS `RUN-1`–`RUN-5`; ADR-0019,
ADR-0020, ADR-0045; open PR #7 (`feat-action_factory`) and PR #26 (`t3/plan-dedup-stages`).

The executor stage (`backend/src/pagercutie/pipeline/executor/`) has stubs for `start_run`, `claim_due_steps`,
`run_step` and `complete_step`, a loop that only logs, and the `runbook_runs` / `step_runs` tables. This plan fills
them in. Each chunk below is one reviewable diff, built by one Sonnet subagent from a self-contained brief (§4). The
coordinator reviews each diff and the next chunk starts only after you approve the previous one.

## 1. What exists and what it depends on

| Piece | State | Consequence for this plan |
|---|---|---|
| `RunbookRun`, `StepRun` models (`alerts/models.py`), `StepStatus`, `StepDecision`, `RunbookRunRead` | On main | No new tables; two additive columns (§2, D2 and D4) |
| `executor/stage.py` messages (`StepJob`, `StepOutcome` union) | On main, stubs | Kept; `run_step` gains a handlers parameter like `dispatch.send` |
| PR #7: gates, `requires_approval`, decision mapping, in-memory `RunbookRun`, `StepInterpreter` | Open, 65 commits behind main | See D1. Its `steps.py` imports `pipeline.executor.actions`, which breaks the import-linter contract "Entity packages do not depend on the pipeline". Its ADR numbers 0040–0044 are taken on main |
| PR #26: `core/templates.py` (`parse`, `render`), `rules.evaluator.template_resolver`, dedup counters | Open | Chunk 3 renders step templates with it, so PR #26 merges first. Its ADR numbers 0061 and 0062 also clash with main |
| `dedup.record`, `routing.route`, `dispatch` | `NotImplementedYet` | The orchestrator cannot run end to end, so executor tests drive the stage directly and set `alerts.occurrences` by hand. Escalation needs recipient resolution that routing will also need (D5) |
| Runbook CRUD (`runbooks/router.py`) and parsing | `NotImplementedYet` | Tests insert `runbooks` rows directly. Text-guard parsing (`retry fails twice` → `StepGuard`) belongs to runbook parsing, not to the executor |

## 2. Decisions

Each needs your call before the chunk that depends on it. The recommendation is marked.

**D1. PR #7.** It solves gates and approval defaults well, but runs actions inline in `RunbookRun.advance()`,
while SPEC §11.3 claims steps from a job table and runs them outside any transaction.

| Option | Tradeoff |
|---|---|
| **Cherry-pick from PR #7 (recommended)** | Chunk 0 copies `gates.py`, `requires_approval`, `_EXPECTED_STATUS` and their tests onto this branch (tested design, exhaustive over `Step`), leaves out `StepBase.run()` so `steps.py` stays a pure contract model (action dispatch becomes an exhaustive `match` in the executor, which restores the `ty` guarantee ADR-0043 traded away), and leaves out the inline runner `RunbookRun.advance()`. One new ADR (next free number after main and PR #26, so 0071 or later) credits and supersedes PR #7's five ADRs. You close PR #7 with a note after talking to Yaroslav, because this reverses ADR-0043 and part of ADR-0040 |
| Rebase PR #7 itself and adapt it there | Keeps its history and authorship; needs edits on another person's branch and their agreement first |
| Ignore PR #7, build from the stubs | No coordination; duplicates work already reviewed in PR #7, and PR #7 then conflicts with everything here |
| Merge PR #7 as is, adapt later | Fastest start; merges an import-linter violation and an in-memory runner that the loop would not use |

**D2. Who applies a human decision.** Entity packages may not import `pipeline`, so `POST …/decision`
(`alerts/service.py`) cannot call `executor.complete_step`.

| Option | Tradeoff |
|---|---|
| **The service records, the executor acts (recommended)** | The service checks permission and the expected status (`409` otherwise), stores the decision in a new nullable `step_runs.decision` column (`StepDecisionKind`), sets `decided_by`, `decided_at`, `run_at = now`, writes the audit entry and sends `NOTIFY steps_pending`. The loop claims the step and applies it. One module owns every transition; the endpoint returns the run with the step still in its awaiting status for up to one poll (≤ 1 s) |
| Shared transition helper in an entity module (`alerts/runs.py`) | The endpoint returns the final state; transition rules then live in two packages and the executor must import an entity helper for its own core logic |

**D3. Wake-ups and leases.** Mirror SPEC §10 for deliveries: `NOTIFY steps_pending` plus a 1 s poll. `run_at`
doubles as the lease: the claim predicate is `run_at IS NOT NULL AND run_at <= now`, with no status filter, and
claiming sets `run_at = now + 30 s`, so a step whose replica died is claimed again (at-least-once, ADR-0008). No new
column. Steps of one run execute in index order: a run has at most one unfinished step with `run_at` set, plus at
most one watching retry (D4). The claim joins `alerts` for `payload` and `occurrences` and reads the run's
per-index `failures` for guards. Settings: `executor_poll_interval`, `executor_lease`, `executor_batch_size`. No
alternative worth listing; this is the existing delivery design.

The loop gets its dependencies the way `listen_worker(engine, handlers, on_lost) -> Worker` does: chunk 4 replaces
the bare `executor.run` in `main.py` with a factory `executor_worker(sessionmaker, settings, integrations, wake) ->
Worker`. `wake` is an `asyncio.Event` that the `steps_pending` handler in the listen map sets; the loop waits on it
with the poll interval as timeout.

**D4. Failed-retry detection (SPEC §11.4, ADR-0020).** A repeat occurrence after a `retry_workflow` ran counts as a
failed retry.

| Option | Tradeoff |
|---|---|
| **Poll `alerts.occurrences` against a baseline (recommended)** | New nullable `step_runs.occurrences_at_run`. When a retry succeeds, store the alert's `occurrences` and keep `run_at` set (watch interval, e.g. 5 s) while later steps of the run are not finished and the alert is not resolved. On claim, a higher count means one failure: `failures += 1`, re-run the retry (`attempts += 1`) and take a new baseline. Any change to `failures` re-arms the run's pending guarded step. Sees every repeat, including `Held` ones that dedup counts in Redis and flushes later |
| Orchestrator calls `executor.record_occurrence` on `Repeated` / `Renotified` | Immediate; misses `Held` repeats, which open no transaction, so "fails twice" may never trigger |

**D5. Escalation without importing routing.** `escalate` resolves the team slug, appends the team to
`alerts.escalated_team_ids`, and creates `pending` deliveries for the target team's on-call by its preferences.

| Option | Tradeoff |
|---|---|
| **Shared recipient resolution in an entity module (recommended)** | E.g. `teams/service.on_call_recipients` plus a delivery-insert helper in `alerts/`, used by `escalate` now and `routing.route` later. Correct now; whoever builds routing must reuse it. Larger than it looks: `teams/service.py` has rotation reads but no on-call computation, `GET /teams/{id}/on-call` and team channel preferences are `501` stubs, and nothing evaluates preference rules by severity yet |
| Escalate only appends `escalated_team_ids` | Small; the target team sees the alert in its feed but nobody is paged, which fails the brief's scenario step 5 |
| `escalate` returns `StepFailed("not available")` until routing lands | No speculative design; the settlement scenario cannot pass |

**D6. Action integrations (SPEC §11.2, ADR-0013 precedent).** One Protocol per integration, injected into `run_step`:
`HttpClient` (`http_get`, `call_webhook`, over `httpx`, 5 s timeout) and `OpsService` (`retry_workflow`,
`restart_service`, `open_ticket`). The default `OpsService` is simulated in-process and returns
`StepSucceeded("simulated: …")`; an HTTP-backed one against `APP_OPS_SERVICE_URL` comes with the mock service in
`compose.yaml` (recommended later, not in this plan). `wait` needs no integration: `complete_step` sets
`run_at = now + seconds`. Alternative: build the mock service now (one more container and chunk for the demo).

**D7. Default approvals.** Adopt PR #7's: `http_get`, `wait`, `manual`, `retry_workflow`, `open_ticket` → `none`;
`restart_service`, `call_webhook`, `escalate` → `required` (the brief's `approval: none` on the retry can only be
legal if its default is `none`). Recorded in SPEC §11.2.

**D8. Attaching runbooks to schemas and alert types (`RUN-1`).** Decided: `start_run` follows `rule.runbook_id`
first; when the rule has none, it picks a runbook whose `attach` condition matches the event. Alert types are
payload conditions (the brief's `matches: {type: WORKFLOW_FAILED}`). For schemas, the event view (SPEC §4.3) gains a
fifth root, `schema`: the event schema's `name`, so `attach` (and rules) can say `schema = settlement-events` and keep
matching across schema versions, which `schema_id` does not.

| Option for schemas | Tradeoff |
|---|---|
| **`schema` root with the schema name (chosen)** | Survives version bumps, readable in YAML, usable by rules too. Touches the rule contract: SPEC §4.3 lists four roots, `contract/rule-tests/paths.json` gains cases, and a bare path `schema` stops reading `payload.schema` (roots win over payload keys, ADR-0062 on PR #26) |
| `schema_ids` column on runbooks | Explicit and indexable; a second way to say "when", tied to IDs unless it stores names |
| Match through a payload field every schema carries | No work; depends on the producer |

Still open inside D8, each with a recommendation:

- Candidates: only runbooks of the event's team (recommended; schema names are unique only within a team, and a
  team should not page through another team's runbook) or every team's.
- Several matches: the first by `created_at` (recommended; predictable, and `runbook_runs.alert_id` allows one run)
  or reject overlapping `attach` conditions at save time (cannot be decided in general for the AST).
- Attach matches are evaluated against the alert's first event, as the run's templates are.

**D9. Scope question (no recommendation without you):**

- `RUN-5` "closes the alert when the problem goes away": what counts as gone? Candidates: every step finished
  without failure and no new occurrence for N minutes; or an explicit `resolve_alert` action. Recommended: a
  separate plan, since it is alert lifecycle, not step execution.

## 3. Chunks

Chunks run in sequence: 2, 3 and 4 all edit `executor/stage.py`, so parallel worktrees would only produce merge
conflicts.

```
0 ──▶ 1 ──▶ 2 ──▶ 2b ──▶ 3 ──▶ 4 ──▶ 5 ──▶ 6a ──▶ 6b ──▶ 7
```

Chunk 1 also freezes the extended `StepJob` that chunks 3 and 4 share: `decision: StepDecisionKind | None`,
`failures_by_index: Mapping[int, int]` (the run's failures per step, for `FailuresGuard`), `occurrences` and
`occurrences_at_run`. Its signature goes into every later brief as frozen.

| # | Chunk | Main files | Tests |
|---|---|---|---|
| 0 | Cherry-pick from PR #7 (D1): `gates.py`, `requires_approval`, `_EXPECTED_STATUS`, their tests; no `StepBase.run()`, no inline runner; one superseding ADR | `pipeline/executor/gates.py`, ADR-0073 | New unit tests (PR #7 has none); `lint:imports` passes. Done |
| 1 | Foundations: audit write helper (`audit/service.record_entry`, actor `None` = system); migration adding `step_runs.decision` and `step_runs.occurrences_at_run` (additive, also on `StepRunRead`); the extended `StepJob`; executor settings (D3) | `audit/service.py`, `alerts/models.py`, `alerts/schemas.py`, `executor/stage.py` (dataclass only), `core/settings.py`, migration, `mise run api` output | Unit: audit helper; integration: migration round trip (`test_migrations.py`) |
| 2 | `start_run`: load the rule's runbook, copy its steps into one `StepRun` per step (`pending`; `run_at = now` for index 0), audit `runbook_run.started`, `NOTIFY steps_pending`; `None` when the rule has no runbook. Idempotent on `runbook_runs.alert_id` | `executor/stage.py` | Integration against Postgres: run created, no runbook, called twice, steps copied (later runbook edits do not change the run) |
| 2b | Attach matching (D8): `Event` gains `schema: str` (the schema name, additive on the message), ingest sets it, `evaluator.event_view` adds the `schema` root; `start_run` falls back to the first team runbook whose compiled `attach` matches when `rule.runbook_id` is null; SPEC §4.3 lists five roots; ADR for D8 | `pipeline/messages.py`, `pipeline/ingest/stage.py`, `rules/evaluator.py`, `pipeline/evaluation/stage.py`, `executor/stage.py`, `contract/rule-tests/paths.json`, SPEC §4.3, §11.1 | Rule contract cases for `schema` (including shadowing a payload key `schema`); integration: rule link wins, attach fallback, other team's runbook ignored, oldest of two matches wins, no match → no run |
| 3 | `run_step` (pure, outside any transaction): render templates with `core/templates.py` from `job.payload`; check gates via chunk 0 (guard → approval → manual) using `job.decision` and `job.failures_by_index`; dispatch the action with an exhaustive `match` to `HttpClient` / `OpsService` (D6). `escalate` returns `NotImplementedYet` until chunk 6 | `executor/stage.py`, `executor/actions.py` | Unit with fake integrations: every action, every gate, every decision kind, template rendering, HTTP error → `StepFailed` |
| 4 | `claim_due_steps`, `complete_step`, loop: claim with `FOR UPDATE SKIP LOCKED` and the lease (D3); map each `StepOutcome` to the row (status, attempts, failures, result, `run_at`), schedule the next step, audit each transition; `executor_worker` factory (D3) waits on `wake` or the poll timeout, runs each job and completes it in its own transaction; `steps_pending` handler in the listen map; wire into `main.py` | `executor/stage.py`, `executor/worker.py`, `main.py` | Integration: two sessions claim disjoint steps; expired lease is reclaimed; every outcome's row and audit entry; `wait` schedules `run_at`; a failed step does not stop the run |
| 5 | Decision endpoint and `GET /alerts/{id}/runbook-run` (D2): permissions per DOMAIN §4 (approve / reject: lead of the alert's or an escalated team; yes / no / done: member or lead), `409` for a step not awaiting that decision, `404` for no run | `alerts/service.py`, `alerts/router.py` | Integration per endpoint: success, `401`, `403`, `404`, `409`; contract test stops skipping both routes |
| 6a | Failed-retry detection (D4): baseline on retry success, watching `run_at`, failure counting, re-run, re-arming guarded steps | `executor/stage.py` | Integration: scenario steps 1–4 (§3.1) |
| 6b | `escalate` (D5). Before writing the brief, the coordinator checks what on-call and preference code exists by then (routing may have landed) and splits this chunk if the recipient helper is not there | `executor/stage.py`, shared recipient helper in `teams/` and `alerts/` | Integration: scenario step 5; unit tests for the recipient helper |
| 7 | Docs pass: SPEC §5.5 table (`run_step` signature), §11.2–§11.4, DOMAIN §6, ADRs for D1–D7, `docs/decisions/README.md` rows | docs only | `mise run contract:check` |

### 3.1 Acceptance scenario (chunks 6a and 6b)

The SPEC §11.4 settlement runbook, driven by calling the stage and the loop body directly, with fake integrations
and `alerts.occurrences` raised by the test in place of dedup:

1. `start_run` → `http_get` runs, `succeeded` with its result.
2. `retry_workflow` runs (attempt 1), baseline stored.
3. Occurrences + 1 → `failures = 1`, retry runs again (attempt 2). `escalate` stays `pending`.
4. Occurrences + 1 → `failures = 2` → `escalate` becomes `awaiting_approval`.
5. A lead approves → the team is in `escalated_team_ids`, `pending` deliveries exist for its on-call, every
   transition and the approval are in the audit log with the actor (`RUN-5`).

## 4. Running the chunks with Sonnet subagents

The coordinator (this session) runs each chunk as one `Agent` call with `model: "sonnet"` and
`subagent_type: "general-purpose"`, in the foreground, on this branch. Subagents start cold, so every brief is
self-contained:

```
Task: chunk N of docs/plans/runbook-executor.md: <one-line goal>.
Read first: AGENTS.md, docs/plans/runbook-executor.md (§2 decisions as approved: <list>), <SPEC/DOMAIN sections>,
  <files to change>, <a similar existing test to copy the style of>.
Frozen signatures (do not change): <signatures from earlier chunks>.
Build: <bullets from the chunk row>.
Tests: <cases from the chunk row>.
Rules: no imports between stages or from entity packages into pipeline; never hand-edit contract/ or
  frontend/src/api/generated/ (run `mise run api`); new routes keep the error-response conventions; no
  `# type: ignore`, `Any`, `cast`; comments say why, sparingly; do not commit.
Finish with: mise run lint, mise run test:unit, mise run test:integration (and mise run api / mise run migration
  -- "..." when a DTO or model changed). Report: files changed, test results with output on failure, any decision
  you made that the brief did not cover.
```

After each chunk the coordinator reads the diff, reruns `mise run lint` and `mise run test`, fixes small findings
itself, runs `/code-review` on chunks 4 and 6a (concurrency and the retry state machine), then asks you to approve and commit
before the next chunk starts.
