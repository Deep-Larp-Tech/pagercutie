# ADR-0043: Team scope in the URL

- **ID:** ADR-0043
- **Timestamp:** 2026-11-21T01:11+01:00
- **Status:** Accepted
- **See:** docs/plans/frontend.md §1 and §4, DOMAIN.md §1, ADR-0023, ADR-0025

## Decision

Team-owned screens live under a path segment with the team slug: `/teams/$team/alerts`, `/teams/$team/rules`,
`/teams/$team/runbooks/…`, `/teams/$team/sources/…`, `/teams/$team/settings/…`. Screens that span teams or belong
to the user stay outside it: `/` (overview), `/alerts/$alertId`, `/me/…`, `/admin/…`.

The last team a user opened is remembered per browser in `localStorage` as a convenience only; the URL is the
source of truth.

## Options

| | `/teams/$team/alerts` (chosen) | `/alerts?team=…` | Global store (zustand) |
|---|---|---|---|
| Shareable links | Yes | Yes | No |
| Type safety | Route params typed by the router | zod-validated search param | Typed, invisible in the URL |
| Fits team-owned entities (rules, runbooks, settings) | Natural nesting | Every page repeats the param | Yes |
| Overview across teams | Separate `/` route | Same route without the param | Same route |

## Rationale

- Rules, runbooks, sources, schemas, rotation and settings are owned by a team (ADR-0026) and permissions come from
  the team role (ADR-0025). Nesting them under `/teams/$team` lets one layout route load the team and the user's
  role once for every child.
- An on-call link pasted into chat must open the same team for the reader; only the URL options give that.
- The slug (ADR-0023) keeps links readable; the layout resolves it to the team id the API needs.
