# ADR-0008: At-least-once delivery with idempotent consumers

- **ID:** ADR-0008
- **Timestamp:** 2026-11-20T20:42+01:00
- **Status:** Accepted, amended by ADR-0043 (idempotent writes stay; offsets, producer and consumer settings are gone)
- **See:** SPEC §5.3, §5.4

## Decision

Consumers commit offsets after writing their results. Alert upserts (by fingerprint) and delivery inserts (by deterministic `delivery_id`) are idempotent. Producers use `acks=all` and idempotence; workers use static membership and the cooperative-sticky assignor.

## Rationale

- No alert is lost on crashes (`DEL-5`), and reprocessing creates no duplicates.
- Static membership lets a restarted worker get its partitions back without a rebalance.
