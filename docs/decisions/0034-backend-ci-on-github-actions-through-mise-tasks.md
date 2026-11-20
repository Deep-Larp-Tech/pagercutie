# ADR-0034: Backend CI on GitHub Actions through mise tasks

- **ID:** ADR-0034
- **Timestamp:** 2026-11-20T23:59+01:00
- **Status:** Accepted
- **See:** SPEC.md §4, ADR-0028

## Decision

`.github/workflows/backend.yml` runs on every pull request and on pushes to `main`. It has five parallel jobs on
`ubuntu-latest`, each calling one mise task:

| Job | Task |
|---|---|
| ruff | `lint:ruff` (`ruff check`, `ruff format --check`) |
| ty | `lint:ty` |
| unit and property tests | `test:unit` (`tests/unit`, `tests/property`) |
| integration tests | `test:integration` (`tests/integration`, Testcontainers) |
| schemathesis | `test:contract` (`tests/contract`, Testcontainers) |

`jdx/mise-action` installs the tools pinned in `mise.toml` and caches them. `UV_LOCKED=1` makes `uv run`
fail on a stale `backend/uv.lock`. The workflow has no `paths` filter.

`test:integration` no longer includes `tests/contract`; `test:contract` runs it. `lint` depends on `lint:ruff` and
`lint:ty`.

## Rationale

- CI calls mise tasks, so local runs and CI run the same commands with the same tool versions.
- The action installs every tool because `mise run` auto-installs missing ones (`task.run_auto_install`), so
  limiting the install would not save the download.
- One job per check names the failing check in the PR status list.
- Schemathesis runs through the existing pytest module, not the `schemathesis run` CLI. The module skips `501`
  stubs (ADR-0028) and migrates a separate `contract` database because schemathesis commits rows. The CLI would
  need a running server, a Postgres service and its own `501` handling, and its `not_a_server_error` check fails
  every stub.
- Unit and property tests share a job because `tests/property` is empty: pytest exits with code 5 when it collects
  no tests, so a property-only job would fail.
- A `paths` filter would leave required checks pending forever on PRs that skip the workflow.
- `contract:check`, `proto:check` and `proto:breaking` (SPEC §4) are not wired into CI yet.
