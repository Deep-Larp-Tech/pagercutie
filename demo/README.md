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

Everything is owned by team `checkout`. Log in as `admin@example.com` or a seeded user to see it.

| Kind | Items |
|---|---|
| Users | `dana.lead@example.com` (lead), `eli.member@example.com`, `fay.member@example.com` (members), all three in the rotation |
| Event schemas | `http-request`, `job-run` (with a `$defs` sub-schema), `host-metric`, `payment-event` |
| Sources | `checkout-api`, `billing-jobs` (webhook); `edge-metrics`, `payments-stream` (WebSocket); `ledger-grpc` (protobuf, skipped while protobuf has no adapter) |
| Rules | Checkout 5xx, Slow checkout requests, Job failed after retries, Disk almost full, Large payment declined, Any critical event |

Every source maps severity from the payload's `level` (`WARNING` to `warn`, and so on). The seed is idempotent,
except that it rotates every source token and rewrites the state file the load reads. Routes that answer 501
(`POST /rules` on main) are reported as skipped.

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
