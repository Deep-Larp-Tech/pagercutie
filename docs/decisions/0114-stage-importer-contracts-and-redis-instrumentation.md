# ADR-0114: Import contracts name each stage's importers; Redis commands are traced

- **ID:** ADR-0114
- **Timestamp:** 2026-11-21T09:12+01:00
- **Status:** Accepted
- **See:** SPEC §5.5, §13, ADR-0045, ADR-0066, `backend/pyproject.toml`, `backend/tests/unit/test_import_contracts.py`,
  `backend/src/pagercutie/core/telemetry.py`

## Decision

**Stage importers.** `backend/pyproject.toml` gains one import-linter `protected` contract per stage entrypoint
module (`pipeline/<stage>/stage.py`), listing the only modules allowed to import it, as the code stands:

| Stage module | Allowed importers besides its own package |
|---|---|
| `ingest.stage` | `orchestrator`, `adapters`, `state`, `main` (builds the schema cache) |
| `evaluation.stage` | `orchestrator`, `adapters`, `state` |
| `dedup.stage` | `orchestrator`, `state` |
| `routing.stage` | `orchestrator` |
| `dispatch.stage` | none |
| `executor.stage` | `orchestrator` |

`tests/unit/test_import_contracts.py` reads `pyproject.toml` and fails when the stage lists of the independence and
orchestrator contracts, the entity package list or the ruff `banned-api` list of `models` modules miss a package
that exists, or when a stage's `stage.py` has no protected contract. import-linter has no option for "every
subpackage", so a test keeps the lists honest.

**Redis spans.** `opentelemetry-instrumentation-redis` 0.66b2, the version of the instrumentation packages already
pinned, traces every command of the replica's Redis client (`RedisInstrumentor.instrument_client` in
`Telemetry.instrument`). Both SQLAlchemy engines (ADR-0110) are instrumented.

| Option | Tradeoff |
|---|---|
| **`opentelemetry-instrumentation-redis`** (chosen) | One dependency of the family already in use; spans for dedup, counters, throttle and rate limit without touching their code. |
| Manual spans around each Redis call | No dependency, but every call site carries tracing code and new ones are missed. |

## Rationale

- SPEC §5.5 said the orchestrator is the only caller of in-request stages; nothing checked it, and `adapters` grew
  imports of three stages. The contract now states who may import what, so the next drift fails `mise run lint`.
- SPEC §13 promises one trace per ingest request covering Redis; without the instrumentation the Redis round trips
  were gaps in the trace.
