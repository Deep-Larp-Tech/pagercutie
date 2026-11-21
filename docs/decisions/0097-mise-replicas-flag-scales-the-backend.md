# ADR-0097: `--replicas` on `mise run stack` and `mise run demo` scales the backend

- **ID:** ADR-0097
- **Timestamp:** 2026-11-21T09:00+01:00
- **Status:** Accepted
- **See:** SPEC §3.2, ADR-0044, `mise.toml`, `demo/README.md`

## Decision

`mise run stack` and `mise run demo` take `-r/--replicas <n>` (default `1`, also read from `BACKEND_REPLICAS`) and
pass it as `docker compose up --scale backend=<n>`. The demo seed and `demo:load` run with `docker compose run
--no-deps`, so they leave the replicas alone. The ceiling is 10, the `BACKEND_PORTS` range (ADR-0044).

| Option | Tradeoff |
|---|---|
| **mise flag, `--scale` on `up`** (chosen) | One discoverable option (`mise run stack --help`); the default `1` makes every `up` deterministic. A bare `docker compose up` still resets to one replica. |
| `deploy.replicas: ${BACKEND_REPLICAS:-1}` in `compose.yaml` | Every compose command agrees, but each one needs the variable exported, and `demo:load` without it scales back to one. |
| Pass `--scale` through `mise run stack -- --scale backend=3` | No new option, but the user must know compose syntax, and the demo task chains two commands, so extra arguments reach only one. |

## Rationale

- `docker compose run` reconciles its dependencies to their default scale: without `--no-deps`, the seed removed
  replicas 2 and 3 right after `up --scale backend=3` had started them.
- `--no-deps` is safe because both tasks start after `up --wait`, which returns once the frontend (and so the
  backend) is healthy.
