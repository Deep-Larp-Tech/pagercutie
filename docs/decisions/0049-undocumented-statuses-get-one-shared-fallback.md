# ADR-0049: Undocumented statuses get one shared fallback

- **ID:** ADR-0049
- **Timestamp:** 2026-11-21T01:30+01:00
- **Status:** Accepted
- **See:** ADR-0028, ADR-0048, `frontend/src/lib/api.ts`

## Decision

The generated fetch client keeps resolving every HTTP status as `{ status, data }`. Screens `switch` on `status`
with one `case` per status the contract documents, and the `default` branch calls
`unexpectedStatusMessage(response)`. That covers `501` stubs, `502` from the proxy and any other status outside the
contract. Its parameter is `never`, so a documented status without a `case` fails `tsc`.

## Rationale

- Error bodies stay typed per status (`409` duplicate slug, `422` field errors), which the forms need.
- The alternative, orval's `forceSuccessResponse`, throws on non-2xx and hands errors to TanStack Query untyped,
  and changes every generated hook's type.
- Every route answers `501` until the backend lands (ADR-0028), so screens need this branch from the start.
