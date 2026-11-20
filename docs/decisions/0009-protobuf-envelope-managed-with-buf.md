# ADR-0009: Protobuf envelope managed with buf

- **ID:** ADR-0009
- **Timestamp:** 2026-11-20T20:45+01:00
- **Status:** Accepted
- **See:** SPEC §4.2

## Decision

Broker messages (`Event`, `Match`, `Delivery`) are protobuf in `contract/proto/pagercutie/v1/messages.proto`, linted, checked for breaking changes and generated (Python + `.pyi`) with buf into `pagercutie.v1`. The user payload is JSON bytes inside the envelope; trace context goes in Kafka headers.

## Rationale

- Typed, compact messages with well-defined evolution rules, safe for rolling deploys.
- The same `.proto` generates Rust types (`prost`) later.
- Keeping the payload JSON means evaluator and dedup handle one format, whatever the source sent.
