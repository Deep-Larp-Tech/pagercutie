# PagerCutie

Flexible alerting and notification service, built for *Hackathon 2026 – Software Engineering*.
It ingests events in any runtime-defined schema, evaluates team rules against them, deduplicates the matches into
alerts, and delivers them on each person's preferred channel together with the team's runbook steps.

| Doc | What's in it |
|---|---|
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | What it must do: requirement IDs, acceptance scenarios from the brief |
| [docs/SPEC.md](docs/SPEC.md) | How it works: architecture, broker topology, contracts, rules, runbooks |
| [docs/DOMAIN.md](docs/DOMAIN.md) | Entities, permissions, lifecycles, management API |
| [docs/DESIGN.md](docs/DESIGN.md) | Frontend design system: themes, colour tokens, motion, components |
| [docs/decisions/](docs/decisions/README.md) | Architecture decision records |

## Quick start

Needs Docker and [mise](https://mise.jdx.dev).

```sh
mise install          # Python, Node, pnpm, uv, buf at the pinned versions
docker compose up -d --build --wait
```

| URL | Service |
|---|---|
| <http://localhost:5173> | Frontend (`/api/*` is proxied to the backend) |
| <http://localhost:8000/docs> | Backend OpenAPI UI (the `api` role) |
| `localhost:19092` | Redpanda (Kafka API) for host processes; `redpanda:9092` inside compose |
| `localhost:5432` | Postgres (`pagercutie` / `pagercutie` / `pagercutie`) |
| <http://localhost:8081> | Redpanda Console, with `docker compose --profile debug up -d` |
| <http://localhost:3000> | Grafana, with `docker compose --profile observability up -d` and `APP_OTEL_ENABLED=true` |

Log in as `admin@example.com` (no password). The backend creates this admin on start while no admin exists; set
`APP_BOOTSTRAP_ADMIN_EMAIL` to use another email.

Ports can be moved with `POSTGRES_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`, `REDPANDA_PORT`, `REDPANDA_CONSOLE_PORT`.

Most management endpoints are contract-first stubs and answer `501 Not Implemented` until they are built
([DOMAIN.md](docs/DOMAIN.md)).

## Development

```sh
mise run up           # Postgres + Redpanda (with topics) in Docker
mise run dev          # backend in every role with reload on :8000 (applies migrations first)
cd frontend && pnpm install && pnpm dev   # frontend on :5173, proxies /api to :8000
```

### Commands

| Command | What it does |
|---|---|
| `mise run stack` | Build and run everything in containers, one service per backend role |
| `cd backend && uv run pagercutie --role=evaluator` | Run one backend role, or `worker` / `all` (SPEC §3.2) |
| `mise run test` | All backend tests (Testcontainers starts its own Postgres; needs Docker) |
| `mise run test:unit` / `test:integration` / `test:contract` | Unit and property, integration, or schemathesis tests |
| `mise run lint` | ruff, ruff format check, ty (`lint:ruff` and `lint:ty` run each half) |
| `mise run migration -- "add alerts"` | Autogenerate an Alembic migration (read and edit it before committing) |
| `mise run migrate` | Apply migrations |
| `mise run api` | Export the contract from the Pydantic DTOs and regenerate the frontend client |
| `mise run contract:check` | Fail if `contract/openapi.json` or the rule / runbook schemas are stale |
| `mise run proto:lint` / `proto:gen` / `proto:check` / `proto:breaking` | Broker protobuf contract (buf) |
| `mise run e2e` | Playwright end-to-end tests |
| `cd frontend && pnpm lint && pnpm build` | Frontend lint, type check and build |

### Changing a contract

| Contract | Source of truth | After editing |
|---|---|---|
| Management API (REST) | Pydantic DTOs in `backend/src/pagercutie/<module>/schemas.py` | `mise run api`, commit `contract/` and `frontend/src/api/generated/` |
| Rule AST, runbook steps | `rules/ast.py`, `runbooks/steps.py` | Same; then fix whatever `ty` and `tsc` report (SPEC §4.4) |
| Broker messages | `contract/proto/pagercutie/v1/messages.proto` | `mise run proto:lint proto:gen`, commit `backend/src/pagercutie/v1/` |

Changes must be additive (SPEC §4.1).

## Repository layout

```
backend/            FastAPI app, one package per entity: router → service → models (src/pagercutie/)
  migrations/       Alembic
  tests/            unit, integration (Testcontainers), contract (schemathesis)
frontend/           React 19 + TanStack, generated API client in src/api/generated/
contract/           openapi.json, rule / runbook JSON Schemas, protobuf (buf module)
docs/               requirements, spec, domain model, decisions
e2e/                Playwright
compose.yaml        Postgres, Redpanda, one service per backend role, frontend, optional console and Grafana
```

## Troubleshooting

- **`port is already allocated`**: another stack holds the port. Stop it, or set e.g. `POSTGRES_PORT=55432`.
- **`migrate` fails with "Can't locate revision"**: the database volume predates a migration history change.
  Reset local data with `docker compose down -v` (deletes the Postgres and Redpanda volumes).
