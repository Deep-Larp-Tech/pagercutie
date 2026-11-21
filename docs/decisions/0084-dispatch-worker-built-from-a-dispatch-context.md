# ADR-0084: Dispatch worker built from a DispatchContext

- **ID:** ADR-0084
- **Timestamp:** 2026-11-21T06:56+01:00
- **Status:** Accepted
- **See:** SPEC §3.2, §5.3 and §10, ADR-0063, `backend/src/pagercutie/main.py`, `backend/src/pagercutie/pipeline/dispatch/worker.py`

## Decision

`create_app` builds a `DispatchContext(sessionmaker, adapters, throttle, settings, wake)` and registers
`dispatch_worker(context)`; there are no module globals and no module-level worker list. The Redis client is also
created in `create_app`, stored on `app.state.redis` for the dedup stage's window store, and closed in the
lifespan after the workers stop.

The loop is woken by `NOTIFY deliveries_pending`: the replica's listener has an async handler that sets
`context.wake`. The listener runs every handler after each reconnect, so deliveries created while the connection
was down are claimed at once. The loop also polls every second, because retries and throttled deliveries have no
`NOTIFY`.

A batch claims `min(delivery_batch_size, MAX_CONCURRENT_SENDS)` rows (at most 16) and sends them all at once. A
full batch makes the loop claim again immediately.

## Rationale

- The dispatcher needs the sessionmaker, the adapters, a Redis client and the settings. Passing them in a frozen
  dataclass keeps tests free to inject fakes and makes a missing adapter a startup error: `build_adapters` covers
  every `Channel`, so a new channel fails type checking.
- The lease is 30 s and an SMTP send can take 10 s. Claiming 50 rows and sending 16 at a time left the last rows
  waiting with their lease running, so another replica could send them again. Claiming only what can be sent at
  once removes the wait; a semaphore with a larger claim would need a lease that grows with the batch.
- Waking on `NOTIFY` keeps a new delivery from waiting for a poll (`NFR-3`); the poll covers what has no signal.
