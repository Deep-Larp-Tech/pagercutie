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

## Quick start

Needs Docker and [mise](https://mise.jdx.dev).

```sh
mise install          # Python, Node, pnpm, uv at the pinned versions
docker compose up -d --build --wait
```

| URL | Service |
|---|---|
| <http://localhost:5173> | Frontend (`/api/*` is proxied to the backend) |
| <http://localhost:8000/docs> | Backend OpenAPI UI (first replica; scaled replicas take 8001–8009) |
| `localhost:5432` | Postgres (`pagercutie` / `pagercutie` / `pagercutie`) |
| `localhost:6379` | Redis |
| <http://localhost:3000> | Grafana (anonymous admin), opens on the PagerCutie dashboard; Explore has Tempo, Prometheus, Loki |
| `localhost:4317`, `localhost:4318` | OTLP gRPC and HTTP receivers of Grafana LGTM |

Log in as `admin@example.com` (no password). The backend creates this admin on start while no admin exists; set
`APP_BOOTSTRAP_ADMIN_EMAIL` to use another email.

Ports can be moved with `POSTGRES_PORT`, `REDIS_PORT`, `BACKEND_PORTS` (a range), `FRONTEND_PORT`, `GRAFANA_PORT`,
`OTLP_GRPC_PORT`, `OTLP_HTTP_PORT`. Set `APP_OTEL_ENABLED=false` to stop the backend exporting telemetry.

Most management endpoints are contract-first stubs and answer `501 Not Implemented` until they are built
([DOMAIN.md](docs/DOMAIN.md)).

## Development

```sh
mise run up           # Postgres, Redis and Grafana LGTM in Docker
mise run dev          # backend with reload on :8000 (applies migrations first, exports telemetry to LGTM)
cd frontend && pnpm install && pnpm dev   # frontend on :5173, proxies /api to :8000
```

### Commands

| Command | What it does |
|---|---|
| `mise run stack` | Build and run everything in containers |
| `docker compose up -d --scale backend=3` | Run three backend replicas behind the Caddy load balancer (SPEC §3.2) |
| `mise run test` | All backend tests (Testcontainers starts its own Postgres; needs Docker) |
| `mise run test:unit` / `test:integration` / `test:contract` | Unit and property, integration, or schemathesis tests |
| `mise run lint` | ruff, ruff format check, ty, import-linter (`lint:ruff`, `lint:ty`, `lint:imports` run each part) |
| `mise run migration -- "add alerts"` | Autogenerate an Alembic migration (read and edit it before committing) |
| `mise run migrate` | Apply migrations |
| `mise run api` | Export the contract from the Pydantic DTOs and regenerate the frontend client |
| `mise run contract:check` | Fail if `contract/openapi.json` or the rule / runbook schemas are stale |
| `mise run e2e` | Playwright end-to-end tests against the compose stack (see `e2e/README.md`) |
| `mise run e2e:ui` | The same tests in Playwright UI mode |
| `cd frontend && pnpm lint && pnpm build` | Frontend lint, type check and build |
| `mise run demo` | Start the stack and seed a demo team, schemas, sources and rules (`demo/README.md`) |
| `mise run demo:load -- --duration 60` | Ingest load over every demo source with a 40 ms network delay |

### Changing a contract

| Contract | Source of truth | After editing |
|---|---|---|
| Management API (REST) | Pydantic DTOs in `backend/src/pagercutie/<module>/schemas.py` | `mise run api`, commit `contract/` and `frontend/src/api/generated/` |
| Rule AST, runbook steps | `rules/ast.py`, `runbooks/steps.py` | Same; then fix whatever `ty` and `tsc` report (SPEC §4.4) |

Changes must be additive (SPEC §4.1).

## Repository layout

```
backend/            FastAPI app, one package per entity: router → service → models (src/pagercutie/)
  migrations/       Alembic
  tests/            unit, integration (Testcontainers), contract (schemathesis)
frontend/           React 19 + TanStack, generated API client in src/api/generated/
contract/           openapi.json, rule / runbook JSON Schemas
demo/               demo seed and ingest load generator (compose overlay)
docs/               requirements, spec, domain model, decisions
e2e/                Playwright
observability/      Grafana dashboard provisioned into Grafana LGTM
compose.yaml        Postgres, Redis, backend (scalable), frontend with the Caddy load balancer, Grafana LGTM
```

## Troubleshooting

- **`port is already allocated`**: another stack holds the port. Stop it, or set e.g. `POSTGRES_PORT=55432`.
- **`migrate` fails with "Can't locate revision"**: the database volume predates a migration history change.
  Reset local data with `docker compose down -v` (deletes the Postgres volume).
