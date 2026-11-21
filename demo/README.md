# Demo

Seeds a demo team and drives ingest load over every source type with 40 ms of network delay (ADR-0087).

```sh
mise run demo                         # start the stack, then seed
mise run demo:load                    # 30 s of load
mise run demo:load -- --duration 120 --concurrency 64 --ws-connections 8
```

Scale the backend first with `docker compose -f demo/compose.yaml up -d --wait --scale backend=3`; the load goes
through Caddy, which balances over the replicas.

## What the seed creates

Everything except the `platform` team is owned by team `checkout`. Log in as `admin@example.com` or a seeded user to
see it.

| Kind | Items |
|---|---|
| Teams | `checkout`; `platform`, the target of the `job-retry` escalate step |
| Users | `dana.lead@example.com` (lead), `eli.member@example.com`, `fay.member@example.com` (members) in `checkout`; `gus.lead@example.com` (lead), `hana.member@example.com` (member) in `platform`; each team's users are its rotation |
| Event schemas | `http-request`, `job-run` (with a `$defs` sub-schema), `host-metric`, `payment-event` |
| Sources | `checkout-api`, `billing-jobs` (webhook); `edge-metrics`, `payments-stream` (WebSocket); `ledger-grpc` (protobuf, skipped while protobuf has no adapter) |
| Runbooks | From [runbooks/](runbooks/), see below |
| Rules | Checkout 5xx, Slow checkout requests, Job failed after retries, Disk almost full, Large payment declined, Any critical event |

| Runbook | Format | Attached to | Shows |
|---|---|---|---|
| `job-retry.yaml` | structured | Job failed after retries, through `matches: {outcome: failed}` | `http_get`, `retry_workflow`, `escalate` with approval behind `retry fails twice` |
| `disk-full.yaml` | structured | Disk almost full | `http_get`, `call_webhook`, `wait`, `manual`, a guard a human answers, `restart_service` with approval, `open_ticket` |
| `checkout-5xx.md` | markdown | Checkout 5xx | Numbered, bulleted and checklist items, a link outside the list, a skipped code fence |
| `payment-declined.md` | markdown | Large payment declined | A checklist |
| `slow-requests.link` | link | Slow checkout requests | One "Open the runbook" step |
| `critical-event.txt` | text | Any critical event | One manual step |

The seed reuses a runbook by slug and never updates it, so a changed file only takes effect on a fresh database
(`docker compose -f demo/compose.yaml down -v`).

Every source maps severity from the payload's `level` (`WARNING` to `warn`, and so on). The seed is idempotent,
except that it rotates every source token and rewrites the state file the load reads. Routes that answer 501 are
reported as skipped.

## Load

`load.py` runs every source on one asyncio event loop in one thread. Each source cycles through payloads of all four
schemas; a share of them matches each rule.

| Flag | Default | Meaning |
|---|---|---|
| `--duration` | 30 | Seconds of load |
| `--concurrency` | 32 | Requests in flight per webhook source |
| `--ws-connections` | 4 | Connections per WebSocket source |
| `--ws-window` | 8 | Unanswered frames per WebSocket connection |

`load.sh` adds the delay with `tc netem` before starting (`DEMO_NET_DELAY`, default `40ms`). netem delays the packets
the load container sends, so every round trip is 40 ms longer; the script prints the `/health` round trip with and
without it. The report lists events, events per second, p50/p95/p99 round trip and a status histogram per source.

Until rule set loading is implemented, ingest answers `501` to every event. `503` right after start means the
replica has not loaded its source catalog yet.

## Running the scripts on the host

```sh
uv run --with httpx==0.28.1 --with websockets==17.4 demo/seed.py
uv run --with httpx==0.28.1 --with websockets==17.4 demo/load.py --duration 10
```

They default to `http://localhost:5173/api` and `./demo-state.json`. No delay is added on the host.
