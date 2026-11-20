# ADR-0006: Python first, Rust gradually

- **ID:** ADR-0006
- **Timestamp:** 2026-11-20T20:38+01:00
- **Status:** Accepted
- **See:** SPEC §3.3

## Decision

Everything starts in Python. Hot paths move to Rust after profiling: first the evaluator as a PyO3 module, then whole roles joining the same consumer groups.

## Rationale

- Fastest to build tonight; the broker architecture allows a role-by-role rewrite.
- Shared contracts (protobuf, JSON Schema) keep both languages compatible.
- A shared evaluator test suite (`contract/rule-tests/`) must pass in both implementations.
