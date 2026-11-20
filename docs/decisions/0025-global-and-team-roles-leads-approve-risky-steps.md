# ADR-0025: Global and team roles; leads approve risky steps

- **ID:** ADR-0025
- **Timestamp:** 2026-11-20T21:24+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §4

## Decision

Users are `admin` or `user`. Per team, members are `lead`, `member` or `viewer`. Leads manage the team and approve risky runbook steps; members work alerts and configuration; viewers read.

## Rationale

- Small enough to implement tonight.
- Matches the brief's "needs approval from the team lead".
