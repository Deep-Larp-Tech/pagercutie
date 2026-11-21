# ADR-0044: Generated MSW mocks in dev, strict MSW in tests

- **ID:** ADR-0044
- **Timestamp:** 2026-11-21T01:12+01:00
- **Status:** Accepted
- **See:** docs/plans/frontend.md "Tests per endpoint" and chunk 0b, ADR-0028, `frontend/src/mocks/`,
  `frontend/src/test/`

## Decision

**Dev.** `pnpm dev:mock` sets `VITE_MOCK=1`; `main.tsx` then imports `src/mocks/browser.ts` dynamically and starts
an MSW service worker (`public/mockServiceWorker.js`) before the first render, with unhandled requests bypassed.
The worker serves every handler orval generates (`get*Mock()` from `src/api/generated/**/*.msw.ts`, aggregated in
`src/mocks/handlers.ts`) unchanged. There are no hand-written fixtures. Data is faker-random per request, so roles
and permissions change on reload. The SSE stream and requests outside `/api` pass the mocks by (ADR-0050), so the feed shows its offline state. Without
the flag, the mock code is dead and left out of the production bundle.

**Tests.** Vitest runs in jsdom with an MSW `setupServer` that starts with no handlers and
`onUnhandledFrame: 'error'` (MSW 3's name for `onUnhandledRequest`), reset after each test. Each test declares the
endpoints it calls with `respond(operation, method, url, status, body)` from `src/test/http.ts`, where `status` and
`body` are typed by the generated response union of that operation.

## Rationale

- Generated handlers follow the contract on every `mise run api`, so mocks never drift and need no upkeep. Fixed
  personas would read better in demos but go stale with each DTO change; the user chose generated-only.
- Random data exercises empty, long and null values that hand-picked fixtures skip.
- A test that reaches an undeclared endpoint fails instead of passing on random data, which keeps the per-endpoint
  coverage in the plan honest.
- MSW works at the network layer, so components use the real generated hooks in both dev and tests.
