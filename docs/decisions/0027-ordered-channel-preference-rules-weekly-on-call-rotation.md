# ADR-0027: Ordered channel preference rules, weekly on-call rotation

- **ID:** ADR-0027
- **Timestamp:** 2026-11-20T21:26+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §5

## Decision

Channel preferences are an ordered list of `{min_severity, channels, window?}`; the first match wins, no match means UI only. Recipients are `user`, `team` or `on_call`; on-call comes from a weekly rotation per team.

## Rationale

- Expresses the brief's working-hours rule ("SMS 08:00–20:00, otherwise email") without a separate fallback concept.
- The brief's Settlements example needs an on-call person; a weekly rotation is the simplest model that works.
