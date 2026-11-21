# ADR-0043: Generated client through a shared fetch mutator

- **ID:** ADR-0043
- **Timestamp:** 2026-11-21T02:30+01:00
- **Status:** Accepted
- **See:** ADR-0028, ADR-0041, ADR-0042, `frontend/orval.config.ts`, `frontend/src/api/fetcher.ts`

## Decision

The orval `api` output sets `override.mutator` to `customFetch` in `frontend/src/api/fetcher.ts`. Every generated
function calls `customFetch<Response>(url, init)`, which resolves to `{ data, status, headers }` for every status,
with the same parsing as orval's default fetch client (`{}` for an empty body or 204, 205, 304, JSON otherwise).
URLs stay relative (`/api/...`) unless `setApiBaseUrl(url)` sets an origin to resolve them against. The browser
app never calls it; the Playwright fixtures call it once per worker so Node can use the same generated functions.

`customFetch` ends with `as T`: orval passes each call site's response union as the type parameter `T`, and a
generic function cannot produce an unconstrained `T` without a cast. The guarantee is the same as before, since
orval's default client ended each function with `as <operation>Response`. Nothing checks the body against the
union at runtime; the e2e setup client relies on the contract test (ADR-0028) for that.

React Query hooks now take per-request options as `request` instead of `fetch` (orval's name with a mutator).

## Rationale

- The e2e fixtures need the generated functions outside a browser, where a relative URL has no origin. A
  hand-written client in `e2e/` would repeat every endpoint and drift from the contract.
- A module-level base URL set by an explicit call keeps the browser app unchanged (Vite proxy, MSW, Caddy) and
  avoids env variables or patching the global `fetch`.
- The mutator keeps the `{ status, data }` unions, so `switch (response.status)` and ADR-0041's fallback still work.
