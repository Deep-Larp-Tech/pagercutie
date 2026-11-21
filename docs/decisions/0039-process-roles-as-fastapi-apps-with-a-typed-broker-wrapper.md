# ADR-0039: Process roles as FastAPI apps with a typed broker wrapper

- **ID:** ADR-0039
- **Timestamp:** 2026-11-21T00:45+01:00
- **Status:** Superseded by ADR-0042 (`core/workers.py` and the lifespan loops remain)
- **See:** SPEC §3.2, §5.4, ADR-0003, ADR-0037, ADR-0038

## Decision

- **Entry point:** `pagercutie --role=<role|worker|all>` (argparse, `pagercutie.cli`) builds the app with
  `create_app` and runs it in one uvicorn process. `APP_ROLES` selects the roles for `fastapi dev`; the default is
  `api` alone, so tests and the contract export need no broker.
- **Runtime:** every role is the same FastAPI app. `/health` is always mounted; `api` adds the management routers;
  consumer roles and the executor add background loops (`core/workers.py`) started and stopped in the lifespan. A
  loop that stops on its own raises SIGTERM, and the process exits 1 after uvicorn's graceful shutdown.
  Startup work that belongs to the API, such as the first-admin bootstrap (ADR-0037), runs only when `api` is
  among the roles.
- **Broker:** a typed wrapper over the synchronous `confluent_kafka` client. `Topic[M]` binds a topic name to its
  protobuf class and partition key (SPEC §5.1); `Producer.produce` awaits the broker ack; `consume` polls in a
  thread and commits each offset after its handler returns. A message that is not valid protobuf is logged and
  skipped.
- **Layout:** `pipeline/{ingest,evaluator,dedup,dispatcher,executor}`. A consumer module exports a `Subscription`
  (topic, consumer group, handler); `main.role_workers` maps each `Role` with an exhaustive `match`.
- **Compose:** one service per role from the one image; only `api` publishes a port.

Considered and rejected:

| Option | Why not |
|---|---|
| Bare asyncio loop plus a small health server for consumer roles | Two shutdown paths and a second HTTP stack for `/health`. |
| `confluent_kafka.aio` | Every method returns `Any`; `cimpl.pyi` types the synchronous client. |
| `aiokafka` | SPEC §3.3 fixes `confluent-kafka`; pure Python and slower. |
| typer for the CLI | A dependency for one flag. |
| Raise in skeleton handlers | Every produced message would be redelivered forever. |
| Fail on undecodable messages | A poison message would block its partition; with only our own producers it is a bug to fix, not data to wait on. |

## Rationale

- One app factory gives every role `/health` (SPEC §13) and SIGTERM handling (SPEC §5.4) without extra code.
- Passing the app object to uvicorn pins one process, so each consumer joins its group once. `fastapi dev`
  reloads still rejoin the group on every code change; acceptable in development.
- Generic `Topic[M]` and `Subscription[M]` make the topic, its message type and its handler agree at type-check
  time.
