# ADR-0015: Rule AST as a Pydantic discriminated union on `op`

- **ID:** ADR-0015
- **Timestamp:** 2026-11-20T20:58+01:00
- **Status:** Accepted
- **See:** SPEC §4.3, §4.4

## Decision

Conditions are Pydantic models (`and`, `or`, `not`, comparisons, `in`, `contains`, `glob`, `exists`) in one union tagged by `op`. The OpenAPI contract, `contract/rule.schema.json` and the TypeScript types are generated from them. New variants are merge-blocked until every consumer handles them (`assert_never`, `satisfies Record<…>`, fixture coverage).

## Rationale

- One definition in Python; no hand-written schema to drift.
- A single tag key lets Python, TypeScript and Rust narrow types with one `match`/`switch`.
- The visual builder edits the AST directly; a textual syntax can be added later on top of it.
