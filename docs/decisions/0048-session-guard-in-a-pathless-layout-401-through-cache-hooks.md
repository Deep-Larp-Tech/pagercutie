# ADR-0048: Session guard in a pathless layout, 401 through the cache hooks

- **ID:** ADR-0048
- **Timestamp:** 2026-11-21T02:45+01:00
- **Status:** Accepted
- **See:** docs/plans/frontend.md chunk 1, DOMAIN.md §2, ADR-0045, ADR-0047, `frontend/src/routes/_app.tsx`,
  `frontend/src/lib/session.ts`, `frontend/src/lib/query.ts`, `frontend/src/router.tsx`

## Decision

**Guard.** Every signed-in screen sits under the pathless layout route `/_app`. Its `beforeLoad` calls
`queryClient.fetchQuery(meQueryOptions)` (`GET /me`): `200` puts `me: MeRead` into the route context, `401` throws
`redirect({ to: '/login', search: { redirect: location.href } })`, any other status throws `UnexpectedStatusError`
with the ADR-0045 message for the layout's error component. `useMe()` reads the context, so components get a
`MeRead` with no loading or error branch. `/login` and `/_tokens` stay outside the layout; `/login` sends a
signed-in user to `/`.

`meQueryOptions` keeps a `200` fresh for 30 s and any other answer for 0 s, so a cached `401` from a `/login`
visit never satisfies the guard. Sign in seeds the query with the login response (no second request) after
`removeQueries()` drops the previous user's data. Sign out calls `queryClient.clear()`.

**Any later 401.** The generated client resolves every status (ADR-0047), so a `401` reaches `onSuccess`, not
`onError`. `createQueryClient({ onUnauthorized })` adds `QueryCache` and `MutationCache` `onSuccess` hooks that
call `onUnauthorized` when the response's `status` is `401`. `createApp()` in `router.tsx` creates the client and
the router together and wires `onUnauthorized` to: do nothing on `/login`; otherwise remove the cached `GET /me`
and navigate to `/login?redirect=<current href>`. The guards' own `GET /me` sets the typed query meta
`handlesUnauthorized: true` (declared on `@tanstack/react-query`'s `Register`) and is skipped by the hook.

The `redirect` search param is a zod-validated optional string; after sign in it is used only when it resolves to
the page's own origin, otherwise the user lands on `/`.

## Options for the later 401

| | Cache `onSuccess` hooks (chosen) | Throw on 401 in `customFetch` | Check in every screen |
|---|---|---|---|
| Type safety | Per-status unions unchanged | `401` leaves every union; errors untyped (ADR-0045 rejected this for all errors) | Unchanged |
| Coverage | Every query and mutation, once | Every call | Only screens that remember |
| Coupling | QueryClient gets a callback; router wired in one place | Mutator would need the router | None, but repeated code |

## Rationale

- A pathless layout loads the session once for every child and leaves `/login` outside it, so the redirect cannot
  loop. Route context gives children a typed `MeRead` without a status switch.
- `fetchQuery` with a status-dependent `staleTime` replaces `ensureQueryData`, which returns cached data however
  stale, including a cached `401`.
- Removing the cached `GET /me` before the redirect stops `/login` from reading a stale `200` and sending the user
  back to the page that just failed.
