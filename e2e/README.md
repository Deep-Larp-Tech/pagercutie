# End-to-end tests

Playwright specs that run against the whole stack: the browser and the generated API client reach the API under
`/api` through the frontend container on :5173 (ADR-0042, ADR-0043).

## Running

Install once from the repo root: `pnpm install`, then `pnpm --filter e2e exec playwright install chromium`.

- `mise run e2e` runs every spec. Playwright starts the stack with `docker compose up --wait` from the repo root
  unless something already answers on :5173 (outside CI). Rebuild containers after backend or frontend changes
  with `mise run stack`, or the specs test old code.
- `mise run e2e:ui` opens the same specs in Playwright UI mode.
- `E2E_BASE_URL=http://host:port mise run e2e` targets a stack that is already running elsewhere.
- `cd e2e && pnpm typecheck` runs `tsc`; it fails when the generated models change shape.

The specs log in as the bootstrap admin, `APP_BOOTSTRAP_ADMIN_EMAIL` (default `admin@example.com`, ADR-0037). Set
the variable in the shell that runs the specs when the stack uses another email.

## Layout

| Path | Holds |
|---|---|
| `tests/<area>/<endpoint>.spec.ts` | One spec per endpoint, e.g. `tests/teams/members.spec.ts` |
| `fixtures/index.ts` | The extended `test`, `expect` and helpers; specs import these from here and the generated functions from `frontend/src/api/generated` |
| `fixtures/api.ts` | `ApiClient`: calls the generated functions with one session's cookie |
| `fixtures/personas.ts` | `asAdmin`, `asLead`, `asMember`, `asViewer`, `asUser`: a logged-in `page` and `api`, plus `user` (and `team`) |
| `fixtures/implemented.ts` | `requireImplemented`, which skips a spec while its route answers `501` |
| `pages/` | Page objects, one per screen, e.g. `LoginPage` |
| `global-setup.ts` | Waits up to 60 s for `GET /api/health` to answer 200 |

Each persona creates its own user, team and membership with a random UUID in the email and slug, so specs run in
parallel without a database reset. Teardown deletes that data once the delete routes are implemented.

## Calling the API

`ApiClient` takes any generated function and infers its arguments and response from it:

```ts
const response = await asUser.api.call(createUser, { email, display_name: "Ann" }); // { status, data } union
expect(response.status).toBe(403);

const user = await adminApi.callExpecting(createUser, 201, { email, display_name: "Ann" }); // UserRead
```

`callExpecting` throws `ApiError` on any other status. In setup, `.catch(skipIfNotImplemented)` turns a `501`
into a skip, as the persona fixtures do.

## Adding a spec for an endpoint

1. Create `tests/<area>/<endpoint>.spec.ts`; import `test`, `expect` and helpers from `../../fixtures`, and the
   endpoint's generated function and URL helper from `frontend/src/api/generated/<tag>/<tag>`.
2. In `test.beforeEach`, call `requireImplemented(adminApi, method, path, body?)` with the path from the URL
   helper. For `GET` pass the path. For `DELETE`, `PUT` and `PATCH` on an item, put `MISSING_ID` in the path, so a
   real route answers `404`. For `POST` pass a body the route must reject without writing, such as a duplicate
   (`409`). The spec then skips with "501: METHOD path not implemented yet" until the backend lands.
3. Write the happy path with the persona allowed to call the endpoint (DOMAIN.md §4), going through the UI once
   the screen exists.
4. Add one permission case with a persona that must not see or do it, and assert the `403` from
   `persona.api.call(...)` or the hidden control on `persona.page`.
5. Run `pnpm typecheck` and `mise run e2e`. New endpoints need no e2e code: `ApiClient` calls any generated
   function.
