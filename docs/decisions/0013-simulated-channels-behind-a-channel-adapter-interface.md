# ADR-0013: Simulated channels behind a channel adapter interface

- **ID:** ADR-0013
- **Timestamp:** 2026-11-20T20:54+01:00
- **Status:** Accepted
- **See:** SPEC §10

## Decision

Email goes to Mailpit; SMS and phone are stored and shown in a simulated phone panel in the UI. Every channel implements one adapter interface.

## Rationale

- The brief allows simulation and judges whether adding a real provider is a small, isolated change (`DEL-4`).
- Mailpit gives a real inbox for the demo video.
