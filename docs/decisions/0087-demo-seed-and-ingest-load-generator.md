# ADR-0087: Demo seed and ingest load generator in a compose overlay, with netem latency

- **ID:** ADR-0087
- **Timestamp:** 2026-11-21T12:00+01:00
- **Status:** Accepted, amended by ADR-0097 (the protobuf source is seeded and loaded over gRPC; build context is the repo root)
- **See:** REQUIREMENTS `ING-1`, `ING-2`, `SCH-1`, SPEC §6 and §7, ADR-0044, ADR-0062, `demo/`

## Decision

**Layout.** `demo/compose.yaml` includes `compose.yaml` and adds two one-shot services in the `demo` profile,
`demo-seed` and `demo-load`, built from `demo/Dockerfile` (Python 3.14, `httpx` and `websockets` at the versions
`backend/uv.lock` pins). They are run with `docker compose run --rm`, so `up --wait` never waits on an exited
container. `mise run demo` starts the stack and seeds; `mise run demo:load -- <flags>` runs the load. Both talk to
`http://frontend:8080/api`, so Caddy balances ingest over the backend replicas the way producers reach it.

**Seed.** Through the management API as the bootstrap admin: team `checkout`, three users (one lead, two members)
with a rotation, four event schemas with disjoint `required` sets, webhook and WebSocket sources (two each), a
`protobuf` source attempt, and six rules. The protobuf create answers 422 (no adapter yet) and `POST /rules`
answers 501 on main; the seed reports both as skipped and goes on. Teams, users, schemas and sources are reused on
rerun; source tokens are rotated every run and written to a state file on the `demo-state` volume.

**Load.** One process, one thread, one asyncio loop. Every source cycles through generators for all four schemas.
Webhook sources keep `--concurrency` requests in flight; WebSocket sources open `--ws-connections` connections and
pipeline `--ws-window` frames on each. The report is a status histogram, events per second and p50/p95/p99 round
trip per source, so 501, 503 and 422 answers are counted, not fatal.

**Latency.** `demo/load.sh` runs `tc qdisc replace dev eth0 root netem delay 40ms` in the load container
(`cap_add: NET_ADMIN`) and prints the `/health` round trip before and after. netem delays egress, so each round
trip gains 40 ms. If `tc` fails the script warns and runs without delay.

## Options for latency

| | netem in the load container (chosen) | Toxiproxy service | Sleep in the client |
|---|---|---|---|
| Realism | Kernel delay on every packet, handshakes included | Real TCP proxy | Fake: one sleep per event, no handshake cost |
| Extra parts | `NET_ADMIN`, `iproute2` | One more service, proxy config | None |
| Scope | Only the load container | Only traffic sent through the proxy | Only the script |

## Options for "one thread"

| | One event loop, many in flight (chosen) | Strictly sequential |
|---|---|---|
| Throughput with 40 ms RTT | Bounded by the server and the in-flight flags | At most 25 events/s per connection |
| Shows | How ingest behaves under load | Mostly the network delay |

## Rationale

- Seeding through the API exercises validation, audit and `NOTIFY` like real use; SQL inserts would skip them.
- Tolerating 501 lets the demo land before rule loading and routing; the same commands report 202 once they do.
- netem is the cheapest option that delays real packets, and it only affects the demo container.
