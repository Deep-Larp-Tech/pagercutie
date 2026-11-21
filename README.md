# PagerCutie

Flexible alerting and notification service, built for *Hackathon 2026 – Software Engineering*.
It ingests events in any runtime-defined schema, evaluates team rules against them, deduplicates the matches into
alerts, and delivers them on each person's preferred channel together with the team's runbook steps.

| Doc | What's in it |
|---|---|
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | What it must do: requirement IDs, acceptance scenarios from the brief |
| [docs/SPEC.md](docs/SPEC.md) | How it works: architecture, shared state, contracts, rules, runbooks |
| [docs/DOMAIN.md](docs/DOMAIN.md) | Entities, permissions, lifecycles, management API |
| [docs/DESIGN.md](docs/DESIGN.md) | Frontend design system: themes, colour tokens, motion, components |
| [docs/decisions/](docs/decisions/README.md) | Architecture decision records |

## Prerequisites

- Docker with Compose v2
- [mise](https://mise.jdx.dev); `mise install` installs the pinned Python 3.14, Node 26, pnpm 12 and uv from
  `mise.toml`

## Run the full stack in containers

```sh
mise install
mise run stack        # docker compose up -d --build --wait
```

Compose starts Postgres, Redis, Mailpit and Grafana LGTM, runs the `migrate` job (`alembic upgrade head`), then
starts the backend and the frontend (Caddy serves the built app and proxies `/api/*` to the backend replicas).

| URL | Service |
|---|---|
| <http://localhost:5173> | Frontend |
| <http://localhost:8000/docs> | Backend OpenAPI UI (first replica; scaled replicas take 8001–8009) |
| `localhost:5432` | Postgres (`pagercutie` / `pagercutie` / `pagercutie`) |
| `localhost:6379` | Redis |
| <http://localhost:8025> | Mailpit web UI, lists the emails the backend sends (SMTP on `localhost:1025`) |
| <http://localhost:3000> | Grafana (anonymous admin), opens on the PagerCutie dashboard; Explore has Tempo, Prometheus, Loki |
| `localhost:4317`, `localhost:4318` | OTLP gRPC and HTTP receivers of Grafana LGTM |

Log in as `admin@example.com` (no password). The backend creates this admin on start while no admin exists; set
`APP_BOOTSTRAP_ADMIN_EMAIL` to use another email.

Run three backend replicas behind the load balancer with `docker compose up -d --scale backend=3` (SPEC §3.2).

Ports can be moved with `POSTGRES_PORT`, `REDIS_PORT`, `MAILPIT_SMTP_PORT`, `MAILPIT_UI_PORT`, `BACKEND_PORTS`
(a range), `FRONTEND_PORT`, `GRAFANA_PORT`, `OTLP_GRPC_PORT`, `OTLP_HTTP_PORT`. Set `APP_OTEL_ENABLED=false` to stop
the backend exporting telemetry.

Stop the stack with `docker compose down`; add `-v` to also delete the Postgres and Grafana volumes.

Most management endpoints are contract-first stubs and answer `501 Not Implemented` until they are built
([DOMAIN.md](docs/DOMAIN.md)).

## Run for development

Backend on the host with reload, infrastructure in Docker:

```sh
mise run dev          # starts Postgres, Redis, Mailpit, Grafana LGTM (mise run up), applies migrations,
                      # then serves the backend on :8000 with reload and telemetry to LGTM
```

Frontend in a second terminal:

```sh
cd frontend
pnpm install
pnpm dev              # :5173, proxies /api to :8000
pnpm dev:mock         # :5173 against msw mocks generated from the contract, no backend needed
```

The backend reads `APP_*` settings from the environment and from `backend/.env`; copy
`backend/.env.example` to `backend/.env` to change the defaults (database and Redis URLs, log level and format,
OTLP endpoint, bootstrap admin email).

## Demo data

```sh
mise run demo                          # start the stack, seed demo teams, schemas, sources, runbooks and rules
mise run demo:load -- --duration 1200 --concurrency 1    # ingest load over every demo source with a 40 ms network delay
```

See [demo/README.md](demo/README.md).

## Commands

| Command | What it does |
|---|---|
| `mise run up` | Postgres, Redis, Mailpit and Grafana LGTM in Docker |
| `mise run dev` | Backend with reload on :8000 (runs `up` and `migrate` first) |
| `mise run stack` | Build and run everything in containers |
| `mise run test` | All backend tests (Testcontainers starts its own Postgres; needs Docker) |
| `mise run test:unit` / `test:integration` / `test:contract` | Unit and property, integration, or schemathesis tests |
| `mise run lint` | ruff, ruff format check, ty, import-linter (`lint:ruff`, `lint:ty`, `lint:imports` run each part) |
| `mise run migration -- "add alerts"` | Autogenerate an Alembic migration (read and edit it before committing) |
| `mise run migrate` | Apply migrations |
| `mise run api` | Export the contract from the Pydantic DTOs and regenerate the frontend client |
| `mise run contract:check` | Fail if `contract/openapi.json` or the rule / runbook schemas are stale |
| `mise run e2e` | Playwright end-to-end tests against the compose stack (see [e2e/README.md](e2e/README.md)) |
| `mise run e2e:ui` | The same tests in Playwright UI mode |
| `cd frontend && pnpm lint && pnpm build` | Frontend lint (oxlint), type check and build |
| `cd frontend && pnpm test` | Frontend unit tests (vitest) |

### Changing a contract

| Contract | Source of truth | After editing |
|---|---|---|
| Management API (REST) | Pydantic DTOs in `backend/src/pagercutie/<module>/schemas.py` | `mise run api`, commit `contract/` and `frontend/src/api/generated/` |
| Rule AST, runbook steps | `rules/ast.py`, `runbooks/steps.py` | Same; then fix whatever `ty` and `tsc` report (SPEC §4.4) |

Changes must be additive (SPEC §4.1).

## Project structure

```
backend/                      FastAPI service (Python 3.14, uv)
  src/pagercutie/
    main.py, asgi.py          app factory and ASGI entry point
    core/                     shared building blocks: settings, db, redis, enums, errors, telemetry, workers
    auth/ users/ teams/       one package per entity: router → service → models, DTOs in schemas.py
    event_schemas/ sources/
    rules/ runbooks/
    alerts/ preferences/
    audit/ health/
    pipeline/                 event processing (SPEC §5)
      messages.py             messages the stages exchange; stages never import each other
      orchestrator.py         wires the stages together
      ingest/                 source authentication, schema matching (SPEC §6, §7)
      evaluation/             cached rule set, evaluator, fingerprints (SPEC §8, §9)
      dedup/                  dedup windows in Redis, alert upserts (SPEC §9)
      routing/                recipients, on-call rotation, channel preferences (SPEC §10)
      dispatch/               throttled delivery through channel adapters (SPEC §10)
      executor/               runbook step execution and approval gates (SPEC §11.3)
    export_openapi.py         contract export used by `mise run api`
    export_schemas.py
  migrations/                 Alembic revisions
  tests/                      unit/, property/ (Hypothesis), integration/ (Testcontainers), contract/ (schemathesis)
frontend/                     React 19 + TanStack app (Vite, pnpm)
  src/routes/                 file-based routes: login, alerts, teams, admin, me
  src/components/             feature components per entity, shared UI in ui/
  src/api/generated/          orval client: react-query hooks, zod schemas, msw mocks (generated)
  Caddyfile                   production static server and /api load balancer
contract/                     openapi.json and rule / runbook JSON Schemas (generated), shared test vectors
demo/                         demo seed, runbooks and ingest load generator (compose overlay)
e2e/                          Playwright tests and page objects
observability/grafana/        dashboard provisioned into Grafana LGTM
docs/                         requirements, spec, domain model, design, decisions, plans
.github/workflows/            backend, e2e and actions-lock CI
compose.yaml                  Postgres, Redis, Mailpit, migrate, backend (scalable), frontend, Grafana LGTM
mise.toml                     pinned tool versions and every task above
```

## Troubleshooting

- **`port is already allocated`**: another stack holds the port. Stop it, or set e.g. `POSTGRES_PORT=55432`.
- **`migrate` fails with "Can't locate revision"**: the database volume predates a migration history change.
  Reset local data with `docker compose down -v` (deletes the Postgres volume).
