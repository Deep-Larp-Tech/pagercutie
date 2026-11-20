# ADR-0003: Modular monolith with process roles

- **ID:** ADR-0003
- **Timestamp:** 2026-11-20T20:25+01:00
- **Status:** Accepted
- **See:** SPEC §3.2

## Decision

One backend codebase and one Docker image, started as `ingest`, `evaluator`, `dedup`, `dispatcher`, `executor` or `api`. `--role=worker` combines the pipeline roles; `--role=all` runs everything in one process with an in-memory queue.

## Rationale

- Monolith speed of development and full static typing inside one codebase.
- Each role still deploys and scales separately for the scalability demo.
- Both modes run the same code behind one `Queue` interface.
