# ADR-0038: Redpanda only, no in-memory queue

- **ID:** ADR-0038
- **Timestamp:** 2026-11-21T00:40+01:00
- **Status:** Superseded by ADR-0042
- **Supersedes:** the in-memory queue and the `Queue` interface in ADR-0003
- **See:** SPEC §3.2, §5

## Decision

Every role talks to Redpanda directly through `core/broker.py`; there is no `Queue` interface and no in-memory
implementation. `--role=all` runs every role in one process against Redpanda, so local development needs Postgres
and Redpanda (`mise run up` starts both).

## Rationale

- The user asked for Redpanda only.
- One implementation means a protocol with a single class behind it; dropping it removes a layer without losing a
  type guarantee.
- Local runs exercise the real partitioning, consumer groups and offset commits instead of a simulation of them.
- Cost: `--role=all` no longer starts without a broker, and broker tests need a Redpanda testcontainer.
