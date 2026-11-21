# ADR-0044: Caddy load-balances the backend replicas

- **ID:** ADR-0044
- **Timestamp:** 2026-11-21T02:08+01:00
- **Status:** Accepted
- **See:** SPEC §3.1, §3.2, `frontend/Caddyfile`

## Decision

The frontend's Caddy is the load balancer. Its `/api/*` proxy uses `dynamic a` upstreams on `{$BACKEND_HOST}`
(default `backend`, re-resolved every 5 s), `lb_policy round_robin`, passive health checks (`fail_duration 10s`)
and `lb_try_duration 5s`. Webhooks, the SSE feed and the UI all enter through it. The compose `backend` service
publishes the host port range `8000-8009` (`BACKEND_PORTS`) so scaled replicas start; the first is on 8000.

| Option | Tradeoff |
|---|---|
| **Existing frontend Caddy** (chosen) | No new service; Docker DNS returns one A record per replica. Frontend and load balancer restart together. |
| Separate Caddy in front of frontend and backend | Cleaner split, one more container to run and configure. |
| Traefik or nginx | Traefik discovers replicas from Docker labels; nginx needs a resolver for scaling. New tool for the team. |

## Rationale

- `docker compose up -d --scale backend=N` is the whole scaling procedure; Caddy picks new replicas up within 5 s.
- Sessions live in Postgres and every replica listens for `NOTIFY alert_changed`, so no sticky sessions are needed.
- Passive checks are used because a replica that refuses connections is detected on the request itself, and the
  request is retried on another replica.
