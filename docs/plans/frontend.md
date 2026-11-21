# Frontend implementation plan

Status: draft for review. Sources: DESIGN.md (Nocturne), DOMAIN.md §2–§7, SPEC.md §12.3, REQUIREMENTS.md `UI-1`–`UI-6`.

Every management route is a `501` stub today, so the frontend is built against MSW until the backend services land.
Each chunk below is one reviewable diff, built by one subagent, and ends with `pnpm lint && pnpm build`,
`pnpm test` (from 0b) and `mise run e2e` (from 0c) passing. The next chunk starts only after you approve the
previous one.

### Tests per endpoint

Every chunk ends with a **Tests** step that covers each endpoint the chunk's screens call, at two levels:

| Level | Tool | Per endpoint |
|---|---|---|
| Component | Vitest + Testing Library + MSW (per-test handler overrides) | Success renders the data; loading shows the skeleton; every error code the route documents (`401`, `403`, `404`, `409`, `422`) shows the message DESIGN.md §10 asks for |
| End-to-end | Playwright against the compose stack (chunk 0c) | Happy path through the UI, plus one permission case (a role that must not see or do it). The spec skips itself while the route answers `501`, like the backend contract test |

An endpoint counts as covered when both specs exist; the chunk's summary lists each endpoint with its spec files.

## 1. Screen map

| Route | Screen | Who sees it | Endpoints |
|---|---|---|---|
| `/login` | Sign in | Logged out | `POST /auth/login` |
| `/` | Overview: my on-call shifts, open alerts across my teams and personal rules | Any user | `GET /me`, `GET /alerts`, `GET /alerts/stream`, `GET /teams/{id}/on-call` |
| `/teams/$team/alerts` | Team live feed (`UI-1`, `UI-2`) | Any team role | `GET /alerts?team_id=`, `GET /alerts/stream?team_id=`, acknowledge, resolve |
| `/alerts/$alertId` | Alert detail: runbook steps, deliveries, history | Any role in the alert's team | `GET /alerts/{id}`, deliveries, runbook-run, decision, `GET /audit` |
| `/teams/$team/rules`, `/rules/new`, `/rules/$ruleId` | Rule list and builder (`UI-3`, `RUL-*`) | List: any role; edit: member, lead | rules CRUD, `POST /rules/test` |
| `/teams/$team/runbooks/…` | Runbooks with parse preview (`RUN-1`, `RUN-8`) | List: any role; edit: member, lead | runbooks CRUD, `POST /runbooks/parse` |
| `/teams/$team/sources/…`, `/teams/$team/schemas/…` | Sources (token rotation) and event schemas | List: any role; edit: member, lead | sources, event-schemas |
| `/teams/$team/settings/general` | Team name and description | Lead, admin | `GET`/`PATCH /teams/{id}` |
| `/teams/$team/settings/members` | Members and roles | List: any role; edit: lead, admin | members `GET`/`PUT`/`DELETE`, `GET /users` |
| `/teams/$team/settings/rotation` | Weekly on-call rotation (`DEL-3`) | List: any role; edit: lead, admin | rotation `GET`/`PUT`, on-call |
| `/teams/$team/settings/notifications` | Team channel preferences (`DEL-2`) | List: any role; edit: lead, admin | team channel-preferences `GET`/`PUT` |
| `/me/profile` | Name, phone, time zone | Self | `PATCH /users/{id}` |
| `/me/notifications` | My channel preferences (Anna's case) | Self | user channel-preferences `GET`/`PUT` |
| `/me/rules/…` | Personal rules | Self | rules with `owner.type = user` |
| `/me/phone` | Simulated phone: my SMS and calls (`DEL-4`) | Self | `GET /me/messages` |
| `/admin/users` | Users: list, create, edit, delete, global role | Admin | users CRUD |
| `/admin/teams` | Teams: list, create, delete | Admin | teams CRUD |

Team scope lives in the URL (`$team` is the team slug), compared in §4.

## 2. Layout

```
┌──────────────┬───────────────────────────────────────────────────────────┐
│ PagerCutie   │  Header: page title · ⌘K search · theme toggle · user menu │
│              ├───────────────────────────────────────────────────────────┤
│ Overview     │  Reconnecting… bar (only when the live feed drops)         │
│ Phone        ├───────────────────────────────────────────────────────────┤
│              │                                                           │
│ TEAM ▾ Settl.│  Page content, max width 1120 px                          │
│  Alerts  (3) │                                                           │
│  Rules       │                                                           │
│  Runbooks    │                                                           │
│  Sources     │                                                           │
│  Settings    │                                                           │
│              │                                                           │
│ ME           │                                                           │
│  My rules    │                                                           │
│  Notifications│                                                          │
│ ADMIN        │                                                           │
│  Users       │                                                           │
│  Teams       │                                                           │
└──────────────┴───────────────────────────────────────────────────────────┘
```

- Sidebar 240 px at ≥1024 px; below that it collapses into a sheet opened from a header button.
- The team switcher lists `me.memberships`; admins also get every team from `GET /teams`. The last team is
  remembered per browser (`localStorage`, convenience only).
- Nav items the user cannot use are hidden, not disabled. Edit buttons inside a page the user can read but not
  change are hidden too; the page states "Only team leads can change this" once, at the top.
- `/login` uses no shell: a centred 360 px card on the page background.

## 3. Chunks

### Chunk 0a: tooling and tokens

- `strict: true` in `tsconfig.app.json`; fix whatever the generated client reports.
- `@/` alias in `tsconfig.json`, `tsconfig.app.json`, `vite.config.ts`.
- `shadcn init` with Base UI and Tailwind v4 (`components.json`), `src/lib/utils.ts` with `cn()`.
- Install `@fontsource-variable/geist`, `@fontsource-variable/geist-mono`, `sonner`, `cmdk`.
- `src/index.css`: all tokens from DESIGN.md §4.1 and §4.2 in both themes, `@theme inline`,
  `@custom-variant dark`, `alert-<colour>` utilities, shadows (§7), motion tokens (§8), reduced-motion rule.
- `index.html`: pre-paint theme script (`theme`, falls back to System).
- `src/lib/layers.ts`, `src/lib/severity.ts` (`defaultColour`, `alertColourClass`, `severityIcon`,
  `severityLabel`, all `satisfies Record<…>`).
- Delete the Vite scaffold (`App.css`, `assets/`, `public/icons.svg`, the demo `App.tsx`).
- A throwaway `/_tokens` page that renders every token and both themes, so you can check them by eye (removed in
  chunk 3).

### Chunk 0b: app skeleton and mocks

- TanStack Router, file-based (`@tanstack/router-plugin`), routes in `src/routes/`; `QueryClient` with
  `retry: false` on 4xx.
- Typed search params with zod `validateSearch` (feed filters).
- MSW in dev behind `VITE_MOCK=1` (`src/mocks/browser.ts`, loaded from `main.tsx` only when the flag is set),
  serving the generated faker handlers (`src/api/generated/**/*.msw.ts`) unchanged. Data is random, so roles and
  permissions change per reload. The SSE stream has no generated handler; under mocks the feed shows its
  offline state.
- Vitest + Testing Library + jsdom config; MSW `setupServer` for tests in `src/test/setup.ts`, with
  `onUnhandledRequest: 'error'` so a test cannot hit an endpoint it did not declare.
- `src/test/render.tsx`: `renderWithProviders(ui, { route, me })` wrapping QueryClient and a memory router.
- `src/test/http.ts`: typed helpers to override one endpoint per test with a status and body, typed by the
  generated response types (`respond(getMeUrl(), 401, …)`).
- UI primitives copied from shadcn and restyled: `Button`, `Input`, `Label`, `Field`, `Select`, `Dialog`,
  `Popover`, `Tooltip`, `DropdownMenu`, `Skeleton`, `Badge`, `Switch`, `ToggleGroup`, `Toaster`.
- **Tests:** one smoke test per helper; `severity.ts` maps cover every `Severity` and `Colour`.

### Chunk 0c: end-to-end test infrastructure

The existing `e2e/` package has a Playwright config that starts the compose stack and no tests. This chunk makes it
ready for one spec per endpoint.

- Layout: `e2e/tests/<area>/<endpoint>.spec.ts` (e.g. `tests/teams/members.spec.ts`), page objects in
  `e2e/pages/`, fixtures in `e2e/fixtures/`.
- `e2e/fixtures/api.ts`: `ApiClient` calls the generated orval functions with a persona's session cookie, through
  the shared fetch mutator `frontend/src/api/fetcher.ts` and `setApiBaseUrl` (ADR-0047), so a contract change
  breaks `tsc` in `e2e/` too (`pnpm typecheck`) and a new endpoint needs no e2e code.
- `e2e/fixtures/personas.ts`: test fixtures `asAdmin`, `asLead`, `asMember`, `asViewer`, `asUser`. Each creates
  its user (and team, membership) through the API with a unique suffix per test, logs in with
  `POST /api/auth/login`, and adds the returned `pc_session` cookie to a fresh browser context, so the test gets a
  signed-in `page` and an `api` client on the same session. Unique data per test keeps
  `fullyParallel: true` working without resetting the database.
- `e2e/fixtures/implemented.ts`: `requireImplemented(api, method, path, body?)` probes the route once per worker
  with the admin's session and calls `test.skip()` with "501: METHOD path not implemented yet" when it is still a
  stub. Mutating methods need a valid body the route must reject (`MISSING_ID` in the path, a duplicate), because
  validation answers `422` before a stub's `501`. Persona fixtures skip on the `501` of their real create calls
  instead (ADR-0046).
- Bootstrap admin: every persona is created by the admin the backend creates from its environment variable (see §4).
- `globalSetup` waits for `/api/health`; `E2E_BASE_URL` keeps working for a stack that is already running.
- `mise run e2e` unchanged; add `mise run e2e:ui` for `playwright test --ui`.
- Real specs `tests/health.spec.ts` and `tests/auth/login.spec.ts` (API-level until chunk 1), and one example
  spec, `tests/users/create-user.spec.ts`, that uses `requireImplemented` and is skipped today.
- A short `e2e/README.md`: how to add a spec for a new endpoint, in five steps.

### Chunk 1: sign in

- `/login`: product name, one-line description, `Field` "Work email", **Sign in** button. Validation from
  `loginRequest` zod schema; `404` shows "No account with that email. Ask an admin to add you." inline.
- No demo-account picker: the screen talks to the backend as it is, email only.
- Session (ADR-0048): the pathless layout `/_app` loads `GET /me` in `beforeLoad` and puts `me` in the route
  context, which `useMe()` reads; a `401` sends the user to `/login?redirect=…`, and so does a `401` from any later
  query or mutation (QueryCache and MutationCache hooks). **Sign out** calls `POST /auth/logout` and clears the
  query cache; until chunk 2 adds the user menu it sits on the placeholder `/` page.
- `src/lib/permissions.ts`: `can(me, action, scope)` with an exhaustive action union from DOMAIN.md §4; the scope
  is the team id, the alert's teams or the user id the action needs, and omitting it is a type error.
- **Tests:** unit tests for every row of the DOMAIN.md §4 table.
  `POST /auth/login`: component (success redirects, `404` message, `422` on a malformed email) and e2e
  (persona signs in and lands on `/`; unknown email stays on `/login`).
  `GET /me`: component (`401` redirects to `/login?redirect=`) and e2e (deep link while logged out comes back
  after sign in).
  `POST /auth/logout`: component (cache cleared) and e2e (after sign out, `/` redirects to `/login`).

### Chunk 2: app shell

- `AppShell`, `Sidebar`, `TeamSwitcher`, `Header`, `UserMenu` (takes over **Sign out**), `ThemeToggle` (View
  Transition cross-fade; the `/_tokens` page uses the same component), `PageHeader`, `EmptyState`, `Sheet`.
- Header: navigation button below 1024 px, page title from the route's `staticData.title` (team name in front
  inside a team), theme toggle, user menu. The `⌘K` search button arrives with the palette in chunk 11.
- Routes: `/` Overview placeholder; `/teams/$team` layout resolves the slug from `me.memberships`, and for admins
  also from `GET /teams?limit=100`, into `team` and `teamRole` in the route context; an unknown or hidden slug shows
  the 404 page. `/teams/$team` redirects to `alerts`. Placeholder pages (PageHeader and "This page isn't built
  yet.") for `alerts`, `rules`, `runbooks`, `sources`, `settings`, `/me/rules`, `/me/notifications`, `/me/profile`,
  `/me/phone`, `/admin/users`, `/admin/teams`; `/admin/*` shows the 404 page to non-admins.
- The last team opened is stored in `localStorage` key `last-team`; on pages outside a team the sidebar uses it, else
  the first team.
- 404 and screen errors render inside the shell (ADR-0049): a splat route `/_app/$` for unknown paths, a
  `notFoundComponent` on every route that throws `notFound()`, and a `CatchBoundary` around the shell's outlet.
- Responsive sheet below 1024 px.
- **Tests:** `GET /teams` (admin team switcher): component (admin sees every team, a user sees only theirs and sends
  no request, `501` falls back to memberships silently, `422` says so) and e2e (admin sees a created team in the
  switcher, a member sees only theirs; both skip while `GET /teams` is a stub). Nav visibility per role: component
  tests driven by `me` (admin sees Admin; viewer, member and lead see the same team pages, since every team role
  may read them); e2e for viewer (team pages, no Admin, 404 on `/admin/users`; skips until `createUser` lands) and
  admin (Admin visible, opens Users). Also 404 inside the shell, theme persistence over reload, and the mobile sheet.

### Chunk 3: overview and live feed

- `SeverityBadge`, `StatusIndicator`, `OccurrenceCounter`, `RelativeTime`, `AlertCard` (open, acknowledged,
  resolved per DESIGN.md §5.1), `AlertFeed` (loading skeleton, empty state linking to the team's rules page),
  `FeedFilters` (status, severity), `ConnectionBar` (connected, reconnecting, offline + **Retry**), `OnCallCard`,
  `LiveAlertFeed` (feed, connection bar and announcer together).
- `useAlertStream(teamId?)`: loads `GET /alerts`, then applies `alert.created` / `alert.updated` from
  `EventSource` into the same query cache entry with the pure reducer in `src/lib/alert-feed.ts`; reconnects with
  backoff and reloads the list on every (re)connect, replaying the events that arrived meanwhile (DOMAIN.md §7,
  ADR-0050). Messages are validated with a zod schema built from the generated `GetAlertResponse`.
- **Acknowledge** and **Resolve** with optimistic update across every cached feed, rollback of the touched alert
  only, sonner toast on success and the error inline on the card; hidden for viewers. A personal rule's alert
  (`team_id: null`) shows the buttons, since only its owner (or an admin) can see it.
- Motion from DESIGN.md §8 (enter, counter bump and tint flash, acknowledge bar solid to dashed, resolve exit after
  700 ms), reduced-motion paths; the status dot pings on open critical alerts only.
- `aria-live` announcer: assertive for new critical and error alerts, polite for the rest.
- `/` Overview: `OnCallCard` per team I belong to ("You're on call until Mon 09:00", "Petra Dvorak is on call",
  "No rotation set"), then one `AlertFeed` over all my teams and personal rules, open and acknowledged only.
- `/teams/$team/alerts`: the same feed for one team, with filters in the search params (zod `validateSearch`;
  absent `status` means open and acknowledged, an empty group means any value).
- `/_tokens` and its building-blocks preview are removed.
- Not shown yet: recipients and channels (not on `AlertRead`; chunk 7 reads deliveries) and the acknowledger's
  name ("Someone is on it" unless it is you).
- **Tests:** stream reducer unit tests (created, updated, out-of-order, reconnect reload, filters).
  `GET /alerts`: component (filters map to query params, empty state, skeleton, `422`, `501`) and e2e (filter by
  status; another team's alerts stay hidden).
  `GET /alerts/stream`: component with a fake `EventSource` (new card appears, counter bumps, connection states,
  reload on reconnect) and e2e (an alert fired through `POST /ingest/{slug}` appears without reload; needs
  `E2E_INGEST_URL`, since compose publishes no ingest port).
  `POST /alerts/{id}/acknowledge` and `/resolve`: component (optimistic update, rollback on `409`, `403`, network
  failure, viewer sees no buttons) and e2e (member acknowledges then resolves; viewer sees no buttons and gets `403`).
  `GET /teams/{id}/on-call`: component (on call, someone else, no rotation, `404`, `422`, `501`) and e2e (no
  rotation; rotation set in setup shows the lead; a member cannot set it).

### Chunk 4: admin

- `/admin/users`: table (name, email, global role, teams), **Add user** dialog (`UserCreate`), edit dialog
  (`UserUpdate`), delete with confirmation. `409` on duplicate email shows inline.
- `/admin/teams`: table (name, slug, members count), **Add team** dialog (`TeamCreate`, slug derived from name
  and editable), delete with confirmation.
- **Tests:** for each of `GET`/`POST /users`, `GET`/`PATCH`/`DELETE /users/{id}`, `GET`/`POST /teams`,
  `PATCH`/`DELETE /teams/{id}`: component (success, `409` duplicate email or slug, `422` field errors under the
  right field, `403`) and e2e (admin creates, edits and deletes; a non-admin opening `/admin/users` gets the 404
  page and the API answers `403`).

### Chunk 5: team settings

- Settings sub-nav: General, Members, Rotation, Notifications.
- Members: list with role; leads add a user (combobox over `GET /users`), change role, remove. A lead cannot
  remove the last lead (client check; the API is the authority).
- Rotation: ordered member list with drag and keyboard reordering, handoff weekday, `HH:MM`, time zone; preview
  of the next four shifts computed from the same rule as DOMAIN.md §5.
- Notifications: `ChannelPreferencesEditor`, an ordered list of `ChannelRule` rows (min severity, channels,
  optional `TimeWindow`), with a plain-language preview per row ("Critical and above: SMS, weekdays 08:00–20:00")
  and a footer "Anything else: UI only". The same component serves `/me/notifications` in chunk 6.
- **Tests:** `GET`/`PATCH /teams/{id}`, `GET /teams/{id}/members`, `PUT`/`DELETE /teams/{id}/members/{user_id}`,
  `GET`/`PUT /teams/{id}/rotation`, `GET`/`PUT /teams/{id}/channel-preferences`: component (success, `403`,
  `422` for an invalid `HH:MM` or empty channel list, shift preview and preference preview text) and e2e (lead
  adds a member, changes a role, reorders the rotation and saves preferences; a member sees all four pages
  read-only).

### Chunk 6: my settings

- `/me/profile`, `/me/notifications` (reuses the editor), `/me/phone` (simulated SMS and call log from
  `GET /me/messages`, styled as a phone screen).
- **Tests:** `PATCH /users/{id}` (self), `GET`/`PUT /users/{id}/channel-preferences`, `GET /me/messages`:
  component (success, `422` on a phone number that is not E.164, empty phone) and e2e (a user saves Anna's two
  preference rules from DOMAIN.md §5 and reloads to see them; another user's preferences answer `403`).

Chunks 7–11 follow the same rule: each lists its endpoints and gets the two specs per endpoint.

### Later chunks, planned after chunk 6

| Chunk | Scope |
|---|---|
| 7 | Alert detail: `StepList` (DESIGN.md §5.3), approve / reject / yes / no / done decisions, deliveries (§5.2), audit history |
| 8 | Rule builder: condition tree editor with field-path `Combobox`, live `POST /rules/test`, routing, presentation with colour pre-fill from severity, dedup window |
| 9 | Runbooks: paste original text, parse preview, attach condition |
| 10 | Sources and event schemas, ingest token rotation, sample payload validation |
| 11 | Command palette (`⌘K`), audit log page |

## 4. Choices

### Team scope: path segment or search param

| | `/teams/$team/alerts` (recommended) | `/alerts?team=…` | Global store (zustand) |
|---|---|---|---|
| Shareable links | Yes | Yes | No |
| Type safety | Route params typed by the router | zod-validated search | Typed, but invisible in the URL |
| Fits team-owned entities (rules, runbooks, settings) | Natural nesting | Every page repeats the param | Yes |
| Overview across teams | Separate `/` route | Same route without the param | Same route |

### Decided

- Mocks: generated faker handlers only, no hand-written fixtures.
- Admin area: users and teams only.
- Sign in: email field against the real `POST /auth/login`, no demo picker.
- One Conventional Commit per approved chunk on this branch.

### Bootstrap admin for end-to-end tests

Decided: the backend creates the first admin from an environment variable on the service, built in a separate PR.
Chunk 0c reads the admin email from the same variable (exact name taken from that PR) and the persona fixtures log
in as that admin to create everyone else. The e2e ADR in chunk 0c records only the frontend side.

### Testing

Component and end-to-end specs per endpoint, as in "Tests per endpoint" above. Visual review is yours, per chunk.

## 5. How chunks are built and reviewed

- One subagent per chunk, run in the foreground, one at a time. Its brief names the files to touch, the DESIGN.md
  and DOMAIN.md sections to follow, and the checks that must pass.
- After each chunk I run the checks myself, open the app against MSW, and send you a summary of what changed,
  screenshots where it helps, and the decisions taken.
- ADRs for decisions that stick (team scope in the URL, faker MSW in dev, strict TypeScript) land with chunk 0b; the e2e
  layout, per-test personas and the bootstrap admin get one with chunk 0c.
