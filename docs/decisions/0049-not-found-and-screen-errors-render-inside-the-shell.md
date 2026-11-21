# ADR-0049: Not-found and screen errors render inside the shell

- **ID:** ADR-0049
- **Timestamp:** 2026-11-21T02:50+01:00
- **Status:** Accepted
- **See:** docs/plans/frontend.md chunk 2, ADR-0043, ADR-0048, `frontend/src/components/shell/app-shell.tsx`,
  `frontend/src/routes/_app/$.tsx`, `frontend/src/routes/_app/teams/$team.tsx`

## Decision

TanStack Router wraps a route's own component in that route's `notFoundComponent` and `errorComponent`, so a
boundary on `/_app` replaces the whole shell. To keep the sidebar and header on every failure of a signed-in
screen:

- **Screen errors.** `AppShell` (the `/_app` component) wraps its `<Outlet />` in the router's `CatchBoundary`,
  reset on path change, rendering `ScreenError`. Child routes set no `errorComponent`, so their render, `beforeLoad`
  and loader errors reach that boundary. `/_app`'s own `errorComponent` (`SessionError`) stays for a failing
  `GET /me`, where there is no user to draw the shell for.
- **Not found from a route.** A route that throws `notFound()` sets its own `notFoundComponent: NotFoundPage`
  (today `/_app/teams/$team` for an unknown or hidden slug and `/_app/admin` for non-admins). The thrown error is
  caught by that route's boundary, which sits inside the shell.
- **Unknown paths.** A splat route `/_app/$` renders `NotFoundPage`, so an unknown path goes through the `/_app`
  guard (signed out: `/login?redirect=…`; signed in: 404 inside the shell). The root `notFoundComponent` renders the
  same page without the shell for anything that escapes both.
- 404 and 403-equivalent cases look the same ("Page not found"), so a URL does not reveal that a team or admin page
  exists.

## Options for unknown paths

| | Splat `/_app/$` (chosen) | Root `notFoundComponent` only | `notFoundComponent` on `/_app` |
|---|---|---|---|
| Shell kept | Yes | No: `/_app` never runs, so the user is unknown | No: replaces the `/_app` component, which is the shell |
| Signed-out deep link | Goes to `/login`, then back to the 404 | Bare 404 | Bare 404 |
| Cost | One route file | None | None |

## Rationale

- A crash or missing page in one screen leaves the sidebar and header usable, so the user moves on without a
  reload.
- One rule (throwing route sets its own `notFoundComponent`; no `errorComponent` below `/_app`) covers every later
  chunk without per-screen boundaries.
