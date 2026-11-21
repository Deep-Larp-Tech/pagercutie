# ADR-0068: One-time secrets bypass the query cache

- **ID:** ADR-0068
- **Timestamp:** 2026-11-21T04:45+01:00
- **Status:** Accepted
- **See:** docs/plans/frontend.md chunk 10, DOMAIN.md §7, ADR-0051, `frontend/src/components/sources/token-dialogs.tsx`

## Decision

`POST /sources/{id}/token` returns the source's ingest token once (`SourceTokenRead`). The frontend calls the
generated fetch function `rotateSourceToken` directly instead of the `useRotateSourceToken` mutation hook. The
token lives only in the dialog's React state and is dropped when the dialog closes. It never goes to the TanStack
Query cache, `localStorage`, logs or toasts. Any later endpoint that returns a secret once follows the same rule.

## Options

| | Generated function, local state (chosen) | Mutation hook, `reset()` on close | Mutation hook with `gcTime: 0` |
|---|---|---|---|
| Token in the mutation cache | Never | Until garbage collection (5 min): `reset()` clears the observer, not the cached mutation | Until the mutation settles and its observer unmounts |
| Visible in Query devtools | No | Yes, while cached | Briefly |
| Typed `{ status, data }` switch (ADR-0049) | Yes | Yes | Yes |
| Code | A `pending` flag by hand | None extra | One option per call site, easy to forget |

## Rationale

- An ingest token lets anyone post events as the source. "Shown only once" should hold in the browser too, not only
  on the server.
- The component test reads the mutation cache and `localStorage` after a rotation and fails if either holds the
  token.
