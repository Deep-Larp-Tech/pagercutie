# ADR-0011: JSON Schema 2020-12 for event schemas, validated with jsonschema-rs

- **ID:** ADR-0011
- **Timestamp:** 2026-11-20T20:50+01:00
- **Status:** Accepted
- **See:** SPEC §7

## Decision

User-defined event schemas are JSON Schema documents stored in Postgres, versioned and immutable. Ingest validates with `jsonschema-rs`.

## Rationale

- Covers sub-schemas, types and value constraints (`SCH-3`) without inventing a format.
- `fastjsonschema` does not support 2020-12; `jsonschema-rs` does, is fast, and is the same engine the Rust port will use.
