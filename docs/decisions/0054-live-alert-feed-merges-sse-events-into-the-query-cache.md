# ADR-0054: Live alert feed merges SSE events into the query cache

- **ID:** ADR-0054
- **Timestamp:** 2026-11-21T03:30+01:00
- **Status:** Accepted
- **See:** ADR-0012, ADR-0048, ADR-0097, DOMAIN.md §6–§7, docs/plans/frontend.md chunk 3,
  `frontend/src/hooks/use-alert-stream.ts`, `frontend/src/lib/alert-feed.ts`

## Decision

- **One store.** `useAlertStream` loads `GET /alerts` with the generated query and writes every `alert.created` and
  `alert.updated` event from `EventSource('/api/alerts/stream?team_id=…')` into that same query cache entry.
  Acknowledge and Resolve update every cached `GET /alerts` entry optimistically and put back only the touched alert
  when the API refuses.
- **Merge rule.** `mergeAlert` is order-independent and idempotent: status, acknowledgement and resolution come from
  the version further along the lifecycle, `occurrences` and `last_seen_at` take the maximum, escalations are
  united. Lists stay in the server's order (most recently seen first).
- **Filters.** An unknown alert is added only when it matches the feed's filters. A known alert that stops matching
  (resolved in an open-only feed) stays for 700 ms and is then pruned, so the resolve shows before the card leaves
  (DESIGN.md §8).
- **Reconnect.** The client closes a failed `EventSource` and reopens it itself: 1 s doubling to 30 s, reset once a
  connection stays open for 5 s. Every open reloads the list and replays the events received while it loaded
  (DOMAIN.md §7). The feed shows "Reconnecting…" at once and "Live updates paused" with Retry after 10 s.
- **Validation.** Each message is parsed with a zod schema assembled from the generated `GetAlertResponse` schema
  (orval drops SSE item schemas); an invalid message is dropped. A JSON null field value becomes the string `"null"`
  because the generated `JsonValue` type is `{}`, which excludes null.
- **Mocks.** `src/mocks/handlers.ts` puts a `bypass` handler before the generated ones. It passes through the
  stream, which the generated handler answers with one random word as `text/event-stream`, so under `VITE_MOCK=1`
  the stream fails at the dev proxy and the feed shows its offline state, as ADR-0048 describes. It also passes
  through every request outside `/api`, because the generated `*/alerts/:alertId` path matches Vite's lazily loaded
  modules (`/src/components/alerts/…`).

## Options for where live state lives

| | Merge into the `GET /alerts` cache entry (chosen) | Separate store (zustand) fed by list and stream | Refetch the list on every event |
|---|---|---|---|
| Correctness on out-of-order events | Merge rule | Same merge rule needed | Server order, but races between refetches |
| Load per event | None | None | One `GET /alerts` per event per open tab |
| Optimistic updates, devtools, `401` handling | Query cache as for every other screen | Second store to keep in sync | Query cache |
| Type safety | Tagged query key types the updater as `listAlertsResponse` | Hand-written store types | Generated types |

## Rationale

- Chunk 7 (alert detail) and the command palette read and change the same alerts; one cache keeps them consistent.
- A merge that only moves forward makes replaying events over a reloaded snapshot safe, which is what DOMAIN.md §7
  asks of a reconnect.
- Resetting the backoff only after a stable connection stops a stream that opens and drops at once (a broken proxy,
  the faker mock) from becoming a tight reload loop.
