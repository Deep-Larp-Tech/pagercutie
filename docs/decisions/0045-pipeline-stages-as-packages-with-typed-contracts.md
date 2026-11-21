# ADR-0045: Pipeline stages as packages with typed contracts and one orchestrator

- **ID:** ADR-0045
- **Timestamp:** 2026-11-21T03:00+01:00
- **Status:** Accepted
- **See:** SPEC §5.5, ADR-0042, ADR-0043

## Decision

- Six stage packages under `pipeline/`: `ingest`, `evaluation`, `dedup`, `routing`, `dispatch`, `executor` (the
  runbook run). Each exposes its entrypoints in `stage.py` and its background loop in `worker.py`.
- Stages exchange frozen Pydantic messages from `pipeline/messages.py`. Dedup returns the union
  `Opened | Renotified | Repeated`, and every consumer matches it exhaustively with `assert_never`.
- `pipeline/orchestrator.py` is the only module that chains the in-request stages and owns their transaction,
  including the dedup window's confirm-after-commit and release-on-failure.
- Dispatch and the executor receive work only through Postgres rows (`deliveries`, `step_runs`).
- Redis and channel providers sit behind Protocols (`WindowStore`, `Throttle`, `ChannelAdapter`).
- import-linter enforces the boundaries in `mise run lint` and CI.
- Unbuilt entrypoints raise `NotImplementedYet`, so the team can implement stages in parallel against fixed
  signatures.

Options considered:

| Option | Tradeoff |
|---|---|
| Packages with direct calls, convention only | Least code; nothing stops one stage from importing another's internals. |
| **Typed contracts, one orchestrator, enforced imports** (chosen) | Boundaries fail the lint; control flow stays in one file; one dev dependency. |
| In-process event bus | Most decoupled; control flow and transaction boundaries are hidden behind a handler registry. |
| A process per stage over HTTP | Physical separation; the broker design's operational cost without its buffering. |

Enforcement tools considered: ruff `banned-api` can only ban a module everywhere, not between two packages. tach is
newer and needs more setup. A hand-written import test is easy to let rot. import-linter expresses
`independence` and `forbidden` contracts directly.

## Rationale

- The user asked for the separation of ingestion, rule evaluation, dedup and runbook runs that the broker gave,
  inside the monolith, with contracts the team can implement in parallel.
- Routing is its own stage: dedup decides whether an alert is new, routing decides who hears about it.
- `Match` carries `RuleRead`, so routing and the executor need no second rule lookup and see the rule as evaluated.
- The orchestrator is a module in the `pipeline` package root, not `pipeline/__init__.py`: importing any
  stage would otherwise import all of them.
