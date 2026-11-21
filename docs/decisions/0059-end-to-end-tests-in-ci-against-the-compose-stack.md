# ADR-0059: End-to-end tests in CI against the compose stack

- **ID:** ADR-0059
- **Timestamp:** 2026-11-21T12:00+01:00
- **Status:** Accepted
- **See:** ADR-0034, ADR-0050, `.github/workflows/e2e.yml`, `e2e/README.md`

## Decision

A separate `e2e` workflow runs on every pull request and on pushes to `main`, in one job on `ubuntu-latest`:
install with `pnpm install --frozen-lockfile`, `pnpm --filter e2e typecheck`, install Chromium with its system
packages, start the stack with `docker compose up --detach --build --wait`, then `mise run e2e`. The pnpm store is
cached by `pnpm-lock.yaml`. On failure the job writes `docker compose logs` next to the Playwright output and
uploads `e2e/test-results/` as the `e2e-results` artifact for 7 days.

Playwright's `webServer.reuseExistingServer` is `true` everywhere, so it uses the stack the workflow started.

## Rationale

- Starting the stack in its own step keeps image builds out of Playwright's 180 s `webServer` timeout and shows a
  build or startup failure as that step's failure, not as a test failure.
- Turning reuse off in CI guarded against a stale stack, and a fresh runner has none.
- A workflow of its own, not a row in the backend matrix: it needs Node, browsers and the whole stack, and takes
  longer than the backend checks, so a slow or failed e2e run doesn't hold their results back.
- Docker layer caching is left out until build time hurts; it needs `docker/build-push-action` and a cache backend.
