# ADR-0042: Scalable monolith instead of the broker pipeline

- **ID:** ADR-0042
- **Timestamp:** 2026-11-21T02:00+01:00
- **Status:** Accepted
- **Supersedes:** ADR-0003, ADR-0004, ADR-0005, ADR-0009, ADR-0010, ADR-0038, ADR-0039
- **See:** SPEC §3, §5, ADR-0043, ADR-0044

## Decision

The backend runs as identical replicas behind a load balancer (ADR-0044), with Postgres as the source of truth and
Redis for shared state (ADR-0043). Every replica serves the management API and ingest, and runs the dispatcher,
counter flush and executor loops. An ingest request validates, evaluates, deduplicates and commits the alert and its
`pending` deliveries before it answers `202`.

Removed: Redpanda, `core/broker.py`, the `pagercutie --role` CLI and `Role` enums, the protobuf contract and buf
tasks, the `events-dlq` topic. The broker implementation is kept on branch `message-broker` (tag
`message-broker-v0`, commit `8b51d9b`) to return to later.

Options for processing an event without a broker:

| Option | Tradeoff |
|---|---|
| **Inline in the ingest request** (chosen) | Accepted means committed, nothing to lose on a crash; ingest latency includes evaluation, and there is no buffer for bursts. |
| Redis Streams with consumer groups | Decouples ingest from evaluation, but is a second broker whose durability depends on Redis persistence settings. |
| In-process asyncio queue | Least code; events accepted but not processed are lost when a replica dies. |

## Rationale

- The user judged the broker pipeline too much to finish before the deadline and chose this design.
- One kind of process means one scaling knob (`--scale backend=N`) and no topic, partition or consumer-group setup.
- Background loops claim Postgres rows with `FOR UPDATE SKIP LOCKED`, so they scale with the replicas without a
  coordinator.
- Cost: no raw event log to replay, and no buffer in front of evaluation; overload shows as latency and `503`
  (SPEC §5.1).
