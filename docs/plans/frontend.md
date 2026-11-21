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
| `/teams/$team/runbooks`, `/runbooks/new`, `/runbooks/$runbookId` | Runbooks with parse preview (`RUN-1`, `RUN-8`) | List: any role; edit: member, lead | runbooks CRUD, `POST /runbooks/parse` |
| `/teams/$team/sources/…`, `/teams/$team/schemas/…` | Sources (token rotation) and event schemas | List: any role; edit: member, lead | sources, event-schemas |
| `/teams/$team/settings/general` | Team name and description | List: any role; edit: lead, admin | `GET`/`PATCH /teams/{id}` |
| `/teams/$team/settings/members` | Members and roles | List: any role; edit: lead, admin | members `GET`/`PUT`/`DELETE`, `GET /users` |
| `/teams/$team/settings/rotation` | Weekly on-call rotation (`DEL-3`) | List: any role; edit: lead, admin | rotation `GET`/`PUT`, on-call |
| `/teams/$team/settings/notifications` | Team channel preferences (`DEL-2`) | List: any role; edit: lead, admin | team channel-preferences `GET`/`PUT` |
| `/me/profile` | Name, phone, time zone | Self | `PATCH /users/{id}` |
| `/me/notifications` | My channel preferences (Anna's case) | Self | user channel-preferences `GET`/`PUT` |
| `/me/rules/…` | Personal rules | Self | rules with `owner.type = user` |
| Drawer on every screen | Sent notifications: deliveries on every channel (`DEL-4`, `DEL-6`), replaces the old `/me/phone` | Any user (own scope; admins all) | `GET /deliveries` |
| `/admin/users` | Users: list, create, edit, delete, global role | Admin | users CRUD |
| `/admin/teams` | Teams: list, create, delete | Admin | teams CRUD |

Team scope lives in the URL (`$team` is the team slug), compared in §4.

## 2. Layout

```
┌──────────────┬───────────────────────────────────────────────────────────┐
│ PagerCutie   │  Header: title · ⌘K · sent notifications · theme · user    │
│              ├───────────────────────────────────────────────────────────┤
│ Overview     │  Reconnecting… bar (only when the live feed drops)         │
│              ├───────────────────────────────────────────────────────────┤
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
  the shared fetch mutator `frontend/src/api/fetcher.ts` and `setApiBaseUrl` (ADR-0051), so a contract change
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
  instead (ADR-0050).
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
- Session (ADR-0052): the pathless layout `/_app` loads `GET /me` in `beforeLoad` and puts `me` in the route
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
- 404 and screen errors render inside the shell (ADR-0053): a splat route `/_app/$` for unknown paths, a
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
  ADR-0054). Messages are validated with a zod schema built from the generated `GetAlertResponse`.
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

- `/admin/users`: table (name, email, global role), **Add user** dialog (`UserCreate`; time zone defaults to the
  browser's), edit dialog (`UserUpdate`, loaded from `GET /users/{id}`), delete with a confirmation naming the user;
  the admin's own row has no **Delete user**. `409` on duplicate email shows inline. No teams column: `UserRead`
  carries no memberships, and listing them would take one request per user.
- `/admin/teams`: table (name linking to `/teams/$team/alerts`, slug, description), **Add team** dialog
  (`TeamCreate`, slug derived from the name until edited), edit dialog (`TeamUpdate`), delete with confirmation
  (a `409` shows the server's reason). No members count, for the same reason as above.
- Both lists load 100 at a time with **Show more** (`useOffsetPages`); team changes refresh `GET /teams` (team
  switcher) and `GET /me`.
- `PATCH` treats `null` as "unchanged", so emptying a phone or description cannot clear it; the dialogs say so
  inline instead of sending a no-op.
- **Tests:** for each of `GET`/`POST /users`, `GET`/`PATCH`/`DELETE /users/{id}`, `GET`/`POST /teams`,
  `PATCH`/`DELETE /teams/{id}`: component (success, every documented error status, `422` field errors under the
  right field, the `501` fallback) and e2e (admin creates, edits and deletes; a non-admin opening `/admin/users`
  gets the 404 page and the API answers `403`).

### Chunk 5: team settings

- Settings sub-nav: General, Members, Rotation, Notifications (child routes; `/teams/$team/settings` opens General).
  Every team role reads all four; leads and admins edit (`team.members.manage`); everyone else sees the values
  without controls and the line "Only team leads can change this." once, under the tabs.
- General: name and description (`PATCH /teams/{id}`); after a save `GET /me` and the admin's `GET /teams` reload, so
  the switcher shows the new name. A set description cannot be cleared: `TeamUpdate` takes a non-empty string or
  `null`, and `null` means unchanged, so the form says so instead of sending it.
- Members: list with role; leads add a user (combobox over `GET /users`, loaded when it first opens), change role
  (saves on pick) and remove (confirmation dialog). The last lead's role and **Remove** are disabled with a note
  (client check; the API is the authority).
- Rotation: on call now (`GET /teams/{id}/on-call`); ordered member list with a drag handle (motion `Reorder`) and
  **Move up** / **Move down** buttons, handoff weekday, `HH:MM`, time zone (combobox; a new rotation starts in the
  lead's own zone); preview of the next four shifts computed from the same rule as DOMAIN.md §5, anchored on the
  on-call answer until the form changes, then "after you save" (ADR-0056).
- Notifications: `ChannelPreferencesEditor` (`src/components/preferences/`), an ordered list of `ChannelRule` rows
  (min severity, channels, optional `TimeWindow`), at most 20, with a plain-language preview per row ("Critical and
  above: SMS, weekdays 08:00 to 20:00") and a footer "Anything else: UI only". It takes `value`, `readOnly` and
  `onSave` (returning saved, field errors or a message), so `/me/notifications` in chunk 6 reuses it unchanged.
- **Tests:** `GET`/`PATCH /teams/{id}`, `GET /teams/{id}/members`, `PUT`/`DELETE /teams/{id}/members/{user_id}`,
  `GET /users`, `GET`/`PUT /teams/{id}/rotation`, `GET /teams/{id}/on-call`, `GET`/`PUT
  /teams/{id}/channel-preferences`: component (success, `403`, `422` for an invalid `HH:MM` or empty channel list,
  `501` fallback, read-only view, last-lead guard, shift preview and preference preview text) in
  `src/components/team-settings/*.test.tsx`, unit tests in `src/lib/{rotation,preferences,local-time,roles}.test.ts`,
  and e2e in `e2e/tests/teams/team-settings-*.spec.ts` (lead adds a member, changes a role, reorders the rotation and
  saves preferences; a member sees all four pages read-only).

### Chunk 6: my settings

- `/me/profile`: display name, phone (E.164, optional), time zone (`TimeZoneSelect`, a searchable list of IANA
  zones); email read-only. `PATCH /users/{id}` sends only the changed fields; **Save profile** stays disabled
  until something changes; "Profile saved" toast; `GET /me` and the router are refreshed so the shell shows the new
  name. `UserUpdate` cannot clear a phone (`null` leaves it unchanged), so the form refuses to empty a stored number.
- `/me/phone` (the simulated phone) was built here and later replaced by the notifications drawer below.
- `/me/notifications` waits for chunk 5's `ChannelPreferencesEditor`; it is wired up after chunk 5 merges, together
  with its `GET`/`PUT /users/{id}/channel-preferences` specs.
- **Tests:** `PATCH /users/{id}` (self): component (`-profile.test.tsx`: success refreshes the shell name and sends
  only the changed field, time zone picked from the list, client and server `422` on a phone that is not E.164,
  a stored phone cannot be emptied, `403`, `501` fallback, unchanged form keeps Save disabled) and e2e
  (`tests/me/profile.spec.ts`: a user edits the profile and reloads; another user's profile answers `403`).

### Notifications drawer (replaces `/me/phone`)

- `NotificationsDrawer`: a non-modal panel on the right of every signed-in screen, opened from the header's **Sent
  notifications** button and remembered in `localStorage` key `notifications-drawer`. From 1024 px the content
  column makes room for it. It lists `GET /deliveries` (new, ADR-0073): deliveries on every channel for alerts the
  user can see, newest first, filtered by channel; polls every 5 s while open, the tab is visible and the endpoint
  answers `200`. `/me/phone`, its sidebar link and its specs are gone; `GET /me/messages` stays in the contract.
- **Tests:** component (`notifications-drawer.test.tsx`: toggle and memory, Escape, newest first with recipient,
  status and failure reason, channel filter maps to `channel`, empty, `501` fallback, polling rule) and e2e
  (`tests/deliveries/list-deliveries.spec.ts`: the drawer opens, survives a reload and closes with Escape, runs
  today; the list and `401` checks skip until `GET /deliveries` is implemented).

### Chunk 7: alert detail

- `/alerts/$alertId` under `/_app`: loads `GET /alerts/{id}` in the component (skeleton while loading); `404` and
  `422` (a malformed id) show the 404 page inside the shell, other statuses the shared fallback with **Try again**.
  Every `AlertCard` title links here.
- `AlertSummary`: the alert in its rule colour (`AlertStatusBar`, extracted from `AlertCard`): severity, status,
  counter, the title as the page's `h1`, body, fields, first and last seen, team, escalated teams, who acknowledged
  and who resolved, and **Acknowledge** / **Resolve** from `useAlertResponse`, which now also writes the cached
  `GET /alerts/{id}`.
- Live updates without a second `EventSource`: `useLiveAlert` merges the fetched alert with the same alert in any
  cached `GET /alerts` entry (`mergeAlert`, ADR-0054). When the merged alert changes status, occurrences or
  escalations, the runbook run, deliveries and history reload, since they have no stream.
- `StepList` (DESIGN.md §5.3): steps in `index` order with action icon, label and one-line description
  (`stepActionInfo`), parameters with `{{…}}` filled from the alert's `payload` in Geist Mono (`renderTemplate`), the
  check question, the guard (a structured guard as a sentence, an unparsed one as the question), status, attempts,
  failures, result and who decided. Decisions per DOMAIN.md §6: **Approve step** (confirmation naming what will run)
  and **Reject step** for `can(me, 'step.approve', alert)`; **Yes** / **No** and **Mark as done** for
  `can(me, 'alert.respond', alert)` or a personal rule's alert; everyone else reads who the step waits for. Each
  decision is optimistic and rolls back on any refusal, with the message under the step (an approval keeps its
  dialog open with the message) and a reload of the run on refusal.
- `DeliveryTable` (`DEL-6`): recipient, channel, `DeliveryStatusLine`, attempts, last error, and the rendered message
  behind **Show message**. Names come only from what the cache already holds (`usePersonName`: you, cached
  `GET /teams/{id}/members` and `GET /users`); anyone else shows as `User 0193c111` with the full id on hover, so the
  page sends no request per person.
- `AlertHistory` (`RUN-5`): `GET /audit?entity_type=alert&entity_id=…&limit=100` as a timeline of actor ("System"
  for `null`), the action in plain words (`auditActionText`; `action` is a free string, so unknown ones are
  humanised) and the time.
- **Tests:** unit tests in `src/lib/{steps,templates,audit}.test.ts`; component tests in
  `src/components/alert-detail/alert-detail.test.tsx`.
  `GET /alerts/{id}`: component (summary, skeleton, `404` and `422` show the 404 page, `501` fallback, network error,
  follows a cached feed entry, acknowledge from the detail, viewer sees no buttons, card title links here) and e2e
  (`tests/alerts/alert-detail.spec.ts`: a member opens the alert from the feed; a user outside the team gets the 404
  page and `404`).
  `GET /alerts/{id}/runbook-run`: component (no runbook, every step status with filled-in parameters, skeleton,
  `404`, `501`) and e2e (`tests/alerts/decisions.spec.ts`: no runbook; parameters filled from the event).
  `POST /alerts/{id}/runbook-run/steps/{index}/decision`: component (viewer, member and lead see only their buttons;
  approve through the dialog; reject, yes, no, done; `409` rollback and reload; `403`, `404`, `400`, `422`; `501`
  fallback) and e2e (`tests/alerts/decisions.spec.ts`: a lead approves; a member sees no Approve and gets `403`; a
  member marks a manual step done and a viewer of the team gets `403`).
  `GET /alerts/{id}/deliveries`: component (rows with names, short ids, status, attempts, last error, message
  toggle; empty; skeleton; `404`; `501`) and e2e (`tests/alerts/deliveries.spec.ts`: the table matches the API; a
  user outside the team gets `404`).
  `GET /audit`: component (query parameters, timeline text, empty, `422`, `501`) and e2e
  (`tests/audit/list-audit.spec.ts`: an acknowledgement shows in the history; a user outside the team gets no
  entries). The e2e specs fire events, so they need `E2E_INGEST_URL` and skip while their routes answer `501`.

Chunks 8–11 follow the same rule: each lists its endpoints and gets the two specs per endpoint.

### Chunk 8: rules and the rule builder

- Routes (ADR-0047, ADR-0070): `/teams/$team/rules` (list), `/teams/$team/rules/new`, `/teams/$team/rules/$ruleId`,
  and the same three under `/me/rules` for personal rules. A rule whose owner does not match the URL (another team,
  someone else's personal rule, also for admins) shows the 404 page.
- List: name (links to the builder) and description, an on switch for members and leads (`PATCH /rules/{id}
  {enabled}`, the switch shows the new state while it saves, errors inline above the table), `SeverityBadge` in the
  rule's colour, recipients in words ("On call in Settlements", "Everyone in Rates", a person's name from
  `GET /users`, "You"), last changed as `RelativeTime`; **New rule**; empty state; 100 per page with **Show more**.
  Viewers read without switches or **New rule** and see "Only members and leads of this team can change its rules."
- Builder sections: Name (name, description, on). When: event schemas (`GET /event-schemas`, any team's), then
  `ConditionEditor` (AND / OR groups two levels deep, **Not** on any node, field path via `FieldPathInput` with
  suggestions from the picked schemas' JSON Schema incl. nested objects and local `$ref`, plus `source`, `severity`,
  `schema_id`; operators from the field type; value input by operator: text, number, yes / no, severity, a list for
  `in`), the condition as a sentence, and `RuleTestPanel` (sample payload JSON, source, severity; `POST /rules/test`
  400 ms after the last change). Who and how: `RecipientsEditor` (on-call person, everyone in a team, one person;
  channel override or each person's settings); a personal rule notifies only its owner. How it looks: title and
  body with **Insert field**, fields on the alert, severity, colour pre-filled from the severity until picked by hand
  (DESIGN.md §4.3), and `RulePreview` (the feed's `AlertCard` filled from the sample event). Noise: dedup fields and
  window in seconds, minutes or hours. Runbook: the team's runbooks (`GET /runbooks?team_id=`), not for personal
  rules.
- **Save rule** (`POST` then back to the list; `PATCH` with only the changed parts and stay), **Delete rule** with
  `ConfirmDialog`, and "Leave without saving?" on navigation and page unload while there are unsaved changes.
- The editor model, its conversion to the AST and the `422` mapping are in ADR-0070. `AlertCard` gained
  `actions={false}` so the preview shows no Acknowledge.
- Contract gaps: `RuleTestRequest` takes no presentation and `RuleTestResult` has no body, so the preview renders
  placeholders in the browser; `409` is documented on no rule endpoint, and `403` / `404` not on `POST /rules/test`,
  so those get the shared fallback (ADR-0049).
- **Tests:** unit tests in `src/lib/{rule-condition,rule-draft,event-fields,templates}.test.ts` (round trips, `not`,
  mixed lists, numbers with grouping, sentence preview for Settlements, Rates and Pricing, `422` paths with the union
  tag, colour pre-fill, dedup window units, `PATCH` diff). Component tests in
  `src/components/rules/rules-page.test.tsx` (`GET /rules` team and personal filters, recipients, empty, viewer,
  `422`, `501`; `PATCH` on switch `200`, `403`, `404`, `422`, undocumented `409`) and
  `src/components/rules/rule-builder.test.tsx` (Team Settlements', Team Rates' and Anna's rules built through the UI
  with the exact `POST /rules` body; client check; colour pre-fill; `POST` `400`, `403`, `404`, `422` under the
  condition node and field, undocumented `409` and `501`; `GET /rules/{id}` fill, other team's rule, someone else's
  personal rule, `404`, `422`, `501`, viewer read-only; `PATCH` diff, `403`, `404`, nested `422`, unsaved-changes
  guard; `DELETE` `204`, `403`, undocumented `409`; `POST /rules/test` matched with the rendered preview, not
  matched, invalid JSON, `400`, `422`, undocumented `403`, `404`, `409`, `501`). E2E in
  `e2e/tests/rules/rules.spec.ts` (list, create through the builder, switch off, rename, delete; viewer read-only
  with `403` from the API; rules hidden from users outside the team) and `e2e/tests/rules/test-rule.spec.ts`, page
  objects in `e2e/pages/rules.ts`; all skip while the routes answer `501`.

### Chunk 9: runbooks

- `/teams/$team/runbooks`: table of the team's runbooks (`GET /runbooks?team_id=`, 100 per page with **Show more**):
  title linking to the runbook, slug, format, number of steps, steps that need approval, "Applies when" (the
  `attach` condition as one line, or "Through rules"), updated. **New runbook** for members, leads and admins
  (`team.config.edit`); viewers read the list with "Only members and leads can change runbooks." once at the top.
- `/teams/$team/runbooks/new` and `/teams/$team/runbooks/$runbookId`: `RunbookEditor` with title, slug (follows the
  title until edited; `RunbookUpdate` has no slug, so it is read-only once saved), format `SegmentedControl` over
  `RunbookFormat` (YAML = `structured`, Markdown, Free text, Link), the original text in a Geist Mono textarea, and
  **Insert example** with the three REQUIREMENTS.md §6.2 samples (`RUN-8`). Viewers opening `/new` get the read-only
  line; viewers opening a runbook get its text and saved steps without controls.
- Live preview: `POST /runbooks/parse` 400 ms after the last change, as a query keyed by format and text
  (ADR-0071), shown as `ParsedStepList`: action icon and label, a plain-language line saying what it does and
  whether it needs approval, parameters with `{{…}}` placeholders highlighted, the question and the guard as
  sentences, and **Needs approval** in primary. Warnings, `422` messages and the parsed condition show beside it.
  An unchanged saved runbook shows its saved steps without a request.
- Condition: `RunbookCreate.attach` is optional and YAML's `matches:` sets it, so the editor sends none and shows the
  parsed condition read-only (sentence plus JSON). Attaching a runbook to a rule belongs to the rule builder
  (chunk 8, `RuleUpdate.runbook_id`).
- **Save runbook** creates (then opens the runbook) or sends only the changed fields; **Delete runbook** asks with
  `ConfirmDialog`; leaving with unsaved changes asks first (TanStack `useBlocker`, plus the browser prompt on
  reload).
- **Tests:** unit tests in `src/lib/runbooks.test.ts` (format map, every condition operator, placeholders) and
  `src/lib/steps.test.ts`, which holds the step helpers chunks 7 and 9 share (action map, stricter-only approval,
  parameters with and without a payload, guards, durations).
  `GET /runbooks`: component (`runbooks-page.test.tsx`: columns, `team_id` and `limit`, skeleton, empty state,
  viewer read-only, `422`, `501`) and e2e (`tests/runbooks/list-runbooks.spec.ts`).
  `POST /runbooks`: component (`runbook-editor.test.tsx`: slug derivation, client validation, body without `attach`,
  `400`/`403`/`404` form errors, `409` under the slug, `422` under the text, `501`, viewer, unsaved-changes dialog)
  and e2e (`create-runbook.spec.ts`: member saves the YAML sample; viewer gets no form and `403`).
  `POST /runbooks/parse`: component (the three samples render their parsed steps, skeleton while the first answer
  loads, one request after typing stops, none for empty text, `400`, `422`, `501`) and e2e (`parse-runbook.spec.ts`; skipped through a real call, since
  `requireImplemented` refuses a `2xx` on `POST`).
  `GET`/`PATCH /runbooks/{id}`: component (`runbook-page.test.tsx`: form filled, saved steps without a parse request,
  skeleton, viewer read-only, another team's runbook, `404`, `422`, `501`, only changed fields sent, `400`/`403`/
  `404`/`422`/`501` on save) and e2e (`update-runbook.spec.ts`).
  `DELETE /runbooks/{id}`: component (confirm and leave, cancel, `403`/`404`/`422`/`501` inline) and e2e
  (`delete-runbook.spec.ts`).

### Chunk 10: sources and event schemas

- `/teams/$team/sources`: table (name, slug, type, ingest URL in Geist Mono with a copy button, token status,
  enabled switch), loaded 100 at a time with **Show more**; empty state; viewers see the list with "On"/"Off", no
  buttons, and "Only members and leads can change this." once. The ingest URL is `SourceRead.ingest_url` as given
  (`/ingest/{slug}` for webhook, `/ingest/{slug}/ws` for WebSocket, ADR-0064). The token column says "Set", or "No
  token yet" in muted text (`has_token` false: ingest answers `404` until a token exists). Members, leads and admins
  (`team.config.edit`) get **New source**, **Create token** next to "No token yet", the switch (`PATCH` with
  `enabled` only) and a row menu with **Edit source**, **Create token** or **Rotate token** (by `has_token`), and
  **Delete source**.
- Source dialog (`SourceFields`): name; slug derived from the name until edited and type, both on create only
  (permanent); one line saying each event is checked against the latest version of each of the team's event schemas
  and the most specific match wins, with a link to `/teams/$team/schemas` (sources carry no schema setting,
  ADR-0065); severity field, value → `Severity` rows and the default severity; **Accept events**. Client checks: a
  severity field when values are listed, no repeated values. Edit loads `GET /sources/{id}` and sends only changed
  fields.
- Token: after **Add source** the dialog offers **Create token**; **Create token** on a tokenless row opens the same
  offer; **Rotate token** asks first ("The current token stops working at once"). A new token reloads the source
  queries so `has_token` updates. The new token shows once in a read-only Geist Mono field with **Copy token**, "This
  token is shown only once.", and a command that sends a test event (`curl` for webhook and protobuf, `websocat` for
  WebSocket) with `Authorization: Bearer …` against `ingest_url` resolved on the page's origin (`NFR-4`). The token
  stays in component state only and goes when the dialog closes (ADR-0072).
- `/teams/$team/schemas`: schemas grouped by name, versions newest first, each version a link; **New schema** for
  editors. `/teams/$team/schemas/$schemaId`: title `name vN`, links to the other versions (`GET
  /event-schemas?name=`), **New version** when the team owns it, the field tree, the JSON Schema, and **Check a
  sample** (`POST /event-schemas/{id}/validate`: "The sample matches the schema." or each `ValidationIssue` with its
  JSON pointer). Any team's schema opens (everyone may read event schemas); one owned by another team says so.
- `/teams/$team/schemas/new` (`?from=<id>` for a new version): name (fixed for a new version), version (1, or the
  name's highest version + 1), description, `JsonEditor` with the line and column of a syntax error inline (own
  RFC 8259 scanner in `src/lib/json-text.ts`, because V8 leaves the offset out of some `JSON.parse` errors), and a
  live field tree (`src/lib/json-schema-tree.ts`: nested objects, array items, `$defs`/`$ref` with a cycle stop,
  `allOf` merged, `oneOf`/`anyOf` options, types and constraints in plain words, `SCH-3`). A `409` on a new name
  points to adding a version; on a new version it says someone saved that number meanwhile.
- Sidebar: **Schemas** under **Sources**.
- **Tests:** component tests in `src/components/sources/sources-page.test.tsx` (`GET`/`POST /sources`,
  `GET`/`PATCH`/`DELETE /sources/{id}`, `POST /sources/{id}/token`: success, skeleton, empty, `400`/`403`/`404`/
  `409`/`422` under the right field including nested severity paths, `501` fallback, viewer read-only, token
  status and **Create token** / **Rotate token** by `has_token`, `has_token` refreshed after a new token, token
  shown once and gone after close, token absent from the query and mutation caches and `localStorage`) and
  `src/components/event-schemas/event-schemas.test.tsx` (`GET`/`POST /event-schemas`, `GET /event-schemas/{id}`,
  `POST /event-schemas/{id}/validate`); unit tests in `src/lib/{json-schema-tree,json-text,ingest-example}.test.ts`;
  e2e in `e2e/tests/sources/sources.spec.ts` and `e2e/tests/event-schemas/event-schemas.spec.ts` with page objects
  `e2e/pages/{sources,event-schemas}.ts`, skipped while the routes answer `501`.

### Chunk 11: command menu and audit log

- `CommandMenu` (`src/components/command-menu/`): cmdk inside the shared `Dialog` (14 px radius, dialog layer), opened
  with `⌘K` / `Ctrl K` (either modifier on every platform) or the header's **Search** button, which shows the
  platform's shortcut. Groups, in order: Alerts, Navigate, Rules in &lt;team&gt;, Runbooks in &lt;team&gt;, Actions.
  - Alerts: open and acknowledged alerts from the Overview's `GET /alerts` cache entry (same params, so it is shared and
    kept live by the stream), merged with every other cached feed; five while the search is empty. `GET /alerts` has
    no text search, so typing filters the loaded list. Enter opens the alert's detail page (`/alerts/$alertId`,
    chunk 7).
  - Acknowledge and Resolve show directly under the highlighted alert, so the next arrow key reaches them; hidden
    unless `can(me, 'alert.respond', alert)` (or the alert has no team, as on `AlertCard`). They reuse
    `useAlertResponse`; the menu stays open, so the button changes in place and an error shows inline.
  - Navigate: every sidebar page the user can see (`can()`), other visible teams as "Switch to &lt;team&gt;", and
    Profile. Phone is left out because the notifications drawer replaces `/me/phone`.
  - Rules and Runbooks: `GET /rules` and `GET /runbooks` for the current team; Enter opens the rule's page
    (chunk 8) or the runbook's page (chunk 9). A failed list shows one muted line in its group; the `501` stub says "This feature isn't
    available yet."
  - Actions: switch the theme; `ThemeToggle` now reads the choice through `subscribeThemeChoice`, so the header
    follows.
- Audit log: `/teams/$team/audit` (team's entries, `team_id` sent) and `/admin/audit` (every entry), linked from the
  sidebar under Settings and under Admin. Table of When (`RelativeTime`), Who ("You", "System" or the actor's short id,
  since `AuditEntryRead` has no name), What (`actionLabel`: `alert.acknowledged` → "Alert acknowledged"; `action` is
  free text, so a readable fallback instead of a closed map), Entity (type in words, a link where a page exists, the
  short id linking to that entity's history) and a disclosure with `data` as JSON in Geist Mono. Filters
  `entity_type` and `entity_id` in typed search params (`auditSearch`, zod); an id that is not a full UUID stays in
  the form with an error. 100 entries per page with **Show more** (`useOffsetPages`).
- **Tests:** `GET /audit`: component (`audit-log.test.tsx`: rows, filters to query params and back, entity history
  link, invalid id, dropped address value, Show more with offsets, skeleton, empty and filtered empty, `422`, `403`
  and `501` through the shared fallback, admin page sends no team, non-admin 404) and e2e
  (`tests/audit/list-audit.spec.ts`: a viewer's page matches the API, filtered empty state, non-admin 404; skipped
  while `GET /audit` is a stub). Command menu: component (`command-menu.test.tsx`: shortcut and label on Mac and
  elsewhere, Escape returns focus after a click and after the shortcut, Navigate per role, typing filters, alert
  search answers from the cache while the server hangs, Enter opens the alert detail, member acknowledges, viewer
  sees no actions, rules open the list page, `501` line, theme switch) and e2e (`tests/shell/command-menu.spec.ts`:
  admin opens it with the shortcut and goes to Users, Escape returns focus, a viewer gets no admin pages).

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
