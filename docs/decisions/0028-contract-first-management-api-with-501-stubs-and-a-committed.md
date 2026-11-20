# ADR-0028: Contract-first management API with 501 stubs and a committed generated client

- **ID:** ADR-0028
- **Timestamp:** 2026-11-20T21:30+01:00
- **Status:** Accepted
- **See:** DOMAIN.md

## Decision

All management endpoints exist as FastAPI routes with Pydantic DTOs that answer `501` until implemented. `mise run api` exports the contract and regenerates the orval client (react-query hooks, zod, msw mocks), which is committed. The contract test skips `501` routes. FastAPI does not split models into input/output schemas.

## Rationale

- Frontend and backend work in parallel from the same contract tonight.
- Each route is contract-tested automatically once implemented.
- One schema per model keeps the recursive rule AST from appearing twice in the client.
