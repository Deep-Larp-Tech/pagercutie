# ADR-0012: Live UI feed over SSE, fed by Postgres NOTIFY

- **ID:** ADR-0012
- **Timestamp:** 2026-11-20T20:52+01:00
- **Status:** Accepted
- **See:** SPEC §12.1

## Decision

The alert feed is Server-Sent Events. Each API replica listens to `NOTIFY alert_changed` and pushes to its browsers.

## Rationale

- The feed is one-way; acknowledge and resolve are plain REST calls.
- The scaffold already uses SSE (`EventSourceResponse`), and it passes through Caddy without extra config.
