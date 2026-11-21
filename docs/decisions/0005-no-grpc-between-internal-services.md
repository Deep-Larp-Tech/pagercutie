# ADR-0005: No gRPC between internal services

- **ID:** ADR-0005
- **Timestamp:** 2026-11-20T20:35+01:00
- **Status:** Superseded by ADR-0042 (no internal services left to call each other)
- **See:** SPEC §4.6

## Decision

Internal roles communicate only through the broker and Postgres. gRPC may still be added as an ingest source adapter.

## Rationale

- Synchronous calls give no buffering, durability or key routing, and add a call chain that must be up end to end.
- Keeping contracts in sync is solved by shared schemas and code generation, not by the transport.
