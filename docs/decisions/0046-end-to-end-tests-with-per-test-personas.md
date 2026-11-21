# ADR-0046: End-to-end tests with per-test personas

- **ID:** ADR-0046
- **Timestamp:** 2026-11-21T02:00+01:00
- **Status:** Accepted
- **See:** docs/plans/frontend.md chunk 0c, ADR-0028, ADR-0037, ADR-0044, ADR-0047, `e2e/README.md`

## Decision

**Layout.** `e2e/tests/<area>/<endpoint>.spec.ts`, page objects in `e2e/pages/`, fixtures in `e2e/fixtures/`.
Specs import `test`, `expect` and helpers from `fixtures/index.ts`, and the generated functions from
`frontend/src/api/generated`. `globalSetup` waits up to 60 s for `GET /api/health` to answer 200. Every request
goes through the frontend proxy (`/api`).

**Generated client.** The fixtures call the generated orval functions (`login`, `getMe`, `createUser`,
`setTeamMember`, ...) through the shared mutator (ADR-0047); an auto worker fixture calls
`setApiBaseUrl(baseURL)`. `ApiClient` in `fixtures/api.ts` holds one session and passes
`{ headers: { cookie } }` as the `RequestInit`. `api.call(op, ...args)` resolves to the generated
`{ status, data }` union; `api.callExpecting(op, status, ...args)` returns the body typed for that status and
throws `ApiError` (function name, status, body) otherwise. Both infer their arguments and result from the
generated function, so a new endpoint needs no e2e code and a contract change fails `pnpm typecheck`. Setup does
not parse responses with zod: the types come from the same contract, and the backend contract test (ADR-0028)
checks the responses. The e2e tsconfig uses `module: esnext` with `moduleResolution: bundler`, because the
generated files use extensionless relative imports.

**Personas.** `asAdmin` logs in as `APP_BOOTSTRAP_ADMIN_EMAIL` (default `admin@example.com`). `asUser`, `asLead`,
`asMember` and `asViewer` are test-scoped: the worker-scoped `adminApi` creates a user with a random UUID in the
email and, for team roles, a team (UUID slug) and a membership. Each persona logs in with the generated `login`,
reads `pc_session` from the response's `Set-Cookie`, and adds it to a fresh browser context with
`context.addCookies`, so its `page` and its `api` share one session. Teardown deletes the team and the user and
ignores a `501` from the delete routes. There is no database reset between tests.

**Skip on `501`.** `requireImplemented(api, method, path, body?)` probes the route once per worker with the
admin's session and skips the test when it answers `501`. The backend checks auth, then validation, then runs the
handler, so the probe must be logged in and well-formed:

| Probe answer | Meaning |
|---|---|
| `501` | Stub; skip the test |
| `401` | The probe had no session; throws |
| `422` | Body or path failed validation before the handler; throws, since a stub would also answer `422` |
| `2xx` on `POST`/`PUT`/`PATCH`/`DELETE` | The probe may have written data; throws |
| anything else | Implemented |

`GET` probes are free of side effects. `PUT`, `PATCH` and `DELETE` on an item use `MISSING_ID` in the path, so a
real route answers `404`. `POST` has no generic side-effect-free probe: the caller passes a body the route must
reject (`POST /users` with the admin's own email answers `409`). Where no such body exists (`POST /teams`), the
fixtures make the real call and skip on its `501`: a stub writes nothing, and a real route creates the data the
test wanted. The probe is a raw `fetch` with the session cookie, since a generated function does not expose its
HTTP method, which the side-effect check needs; specs build the path with the generated URL helper.

## Rationale

- Unique data per test keeps `fullyParallel: true` working against a long-lived stack. A reset route or a
  per-test database would need test-only backend code or a container per worker.
- The admin comes from the same setting the backend reads (ADR-0037), so the specs need no seed SQL.
- Calling the generated functions keeps one client for the app and the tests. A hand-written e2e client repeated
  each endpoint, and zod parsing in setup would duplicate what the contract test checks.
- Skipping on `501` matches the backend contract test (ADR-0028), so specs can land before their routes.
