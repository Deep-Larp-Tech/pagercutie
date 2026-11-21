# ADR-0004: Redpanda (Kafka API) as the message broker

- **ID:** ADR-0004
- **Timestamp:** 2026-11-20T20:30+01:00
- **Status:** Superseded by ADR-0042 (kept on branch `message-broker`, tag `message-broker-v0`)
- **See:** SPEC §5

## Decision

The high-volume event path runs through Redpanda. Postgres only holds low-volume state (rules, alerts, deliveries, audit).

## Rationale

- Postgres load grows with alerts, not events: no obvious bottleneck on the hot path (`NFR-2`).
- The broker gives durability, buffering during restarts and key-based routing.
- Kafka-compatible: same clients, swappable for Apache Kafka by changing the image. Single container, fast start, no JVM.
- RabbitMQ rejected: no partition-key affinity or replay out of the box.
