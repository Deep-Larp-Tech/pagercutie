# Load-test plan

`NFR-3` asks for measured throughput and latency. Nothing has been measured yet: SPEC §5.1 ("throughput is
replicas × per-replica rate", "the scaling lever is more replicas, then Postgres") and ADR-0042 ("background loops
scale with the replicas") are claims until this plan's results table is filled in. Record real numbers only; a run
that failed is recorded as failed.

## What to run

The generator is `demo/load.py` (ADR-0087), through Caddy, with 40 ms of netem delay.

```sh
mise run demo
# Throughput runs: lift the per-source limit so it does not cap the result (ADR-0111).
APP_INGEST_SOURCE_RATE_PER_SECOND=100000 APP_INGEST_SOURCE_BURST=100000 \
  docker compose -f demo/compose.yaml up -d --wait --scale backend=1
mise run demo:load -- --duration 120 --concurrency 32 --ws-connections 4 --ws-window 8
mise run demo:load -- --duration 120 --concurrency 64 --ws-connections 8 --ws-window 8
# Repeat both with --scale backend=3.
```

Run each combination three times and keep all three rows. Wait 30 s between runs so the counter flush and the
dispatcher drain, and note the commit you measured.

For the commit-latency numbers, start Postgres with `pg_stat_statements` for these runs only (a compose override,
not committed): `command: ["postgres", "-c", "max_connections=200", "-c",
"shared_preload_libraries=pg_stat_statements", "-c", "pg_stat_statements.track_utility=on"]`, then
`CREATE EXTENSION pg_stat_statements;` and `SELECT pg_stat_statements_reset();` before each run.

## What to record

| Number | Where it comes from |
|---|---|
| Events/s accepted | `load.py` report, `all` row, and `sum(rate(events_ingested_total[1m]))` |
| Ingest round trip p50 / p99 | `load.py` report, per source |
| End-to-end latency p50 / p99 | `histogram_quantile(0.5 \| 0.99, sum by (le) (rate(end_to_end_latency_seconds_bucket[1m])))` |
| Refused requests | `load.py` status histogram (429, 503) and `sum by (reason) (increase(ingest_refused_total[2m]))` |
| Postgres connections, peak | `SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'pagercutie' GROUP BY state;` every 5 s |
| Held to Postgres-path ratio | `sum(increase(dedup_outcomes_total{path="redis"}[2m])) / sum(increase(dedup_outcomes_total{path="postgres"}[2m]))` |
| Postgres-path matches without a won claim | `sum by (reason) (increase(dedup_fallback_total[2m]))` |
| Commit latency | `SELECT calls, mean_exec_time, max_exec_time, stddev_exec_time FROM pg_stat_statements WHERE query = 'COMMIT';` |
| Notifications sent | `SELECT calls FROM pg_stat_statements WHERE query LIKE '%pg_notify%';` per run, divided by the run length |
| Backend CPU per replica | `docker stats --no-stream` during the run |

### Notifying commits (review finding 8)

The architecture review counted three `pg_notify` calls per opened alert and one per counter in each counter flush
batch, up to 500 per batch (`pipeline/dedup/`). Postgres serialises the commit of notifying transactions on a global lock, so
this may cap alert creation and flush throughput. It is an estimate: compare the `COMMIT` mean and max with the
notification rate across the 1- and 3-replica runs before changing anything. If commit latency grows with the
notification rate while CPU stays low, batching the flush notifications is the first candidate.

## Results

No run has been recorded yet.

| Date | Commit | Replicas | Concurrency | Events/s | Ingest p50 / p99 | End-to-end p50 / p99 | Peak connections | Held : Postgres | COMMIT mean / max | Notifications/s | 429 / 503 |
|---|---|---|---|---|---|---|---|---|---|---|---|
