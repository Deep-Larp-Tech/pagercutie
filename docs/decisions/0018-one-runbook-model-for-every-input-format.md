# ADR-0018: One runbook model for every input format

- **ID:** ADR-0018
- **Timestamp:** 2026-11-20T21:04+01:00
- **Status:** Accepted
- **See:** SPEC §11.1

## Decision

Runbooks keep their original text and are parsed into steps: structured YAML validates directly, Markdown list items become manual steps, unknown text becomes one manual step. An LLM-suggested structured version (reviewed by a human) is optional.

## Rationale

- Judges will bring formats we have not seen (`RUN-8`): everything always displays, and what we understand becomes executable.
