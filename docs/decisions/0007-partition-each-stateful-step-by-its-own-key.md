# ADR-0007: Partition each stateful step by its own key

- **ID:** ADR-0007
- **Timestamp:** 2026-11-20T20:40+01:00
- **Status:** Accepted
- **See:** SPEC §5.1, §5.2

## Decision

`events` is unkeyed, `matches` is keyed by `rule_id:fingerprint`, `deliveries` by `recipient_id`; 12 partitions each, fixed. Dedup windows and throttle counters live in worker memory.

## Rationale

- The fingerprint is only known after rule evaluation, so `events` cannot be keyed by it.
- One consumer per partition means per-key state needs no shared store or locks on the hot path.
- A broker failure only moves partition leadership; key→partition and partition→worker mappings stay, so in-memory state stays valid.
