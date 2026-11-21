# ADR-0102: Continuous dispatch and the UI notify sent with `complete`

- **ID:** ADR-0102
- **Timestamp:** 2026-11-21T12:00+01:00
- **Status:** Accepted
- **See:** ADR-0084, SPEC §5.3, §10 and §13, `backend/src/pagercutie/pipeline/dispatch/worker.py`,
  `backend/src/pagercutie/pipeline/dispatch/stage.py`, `backend/src/pagercutie/pipeline/dispatch/channels/ui.py`

## Context

With one replica under `mise run demo:load` (CPU-bound event loop), Tempo traces and delivery timestamps gave an
end-to-end UI latency of p50 ~690 ms and p99 ~2.4 s. Commit to dispatcher pickup was p50 136 ms and p99 1.5 s:
`dispatch_once` claimed up to 16 rows and waited on `asyncio.gather` for every send and `complete` before claiming
again, so a delivery committed mid-batch waited for the slowest send. The send segment was p50 139 ms, mostly the UI
adapter waiting for a pool connection for a transaction that only sent `NOTIFY alert_changed`.

## Decision

- **Continuous dispatch.** `dispatch_loop` keeps at most `claim_limit` (`min(delivery_batch_size, 16)`) sends in
  flight as tasks and claims only as many rows as there are free slots. It claims after `NOTIFY deliveries_pending`
  set `wake`, after the 1 s poll interval, or when its previous claim filled every free slot and a slot has freed
  since. A freed slot alone does not claim when the previous claim came back short, since nothing more was due then
  and anything new brings a wake or waits for the poll. ADR-0084's guarantee holds: every claimed row starts sending
  at once, so none waits for a slot with its lease running. On `stopping` the loop stops claiming and waits for the
  sends in flight. `dispatch_once` is removed.
- **UI notify in `complete`.** `UiAdapter.send` does no I/O and returns `Sent`. `_complete_sent` sends
  `alert_changed` with `alert.updated` in the transaction that marks the delivery `sent` when
  `announces_on_sent(channel)` is true; that function matches `Channel` exhaustively with `assert_never`, like
  `is_throttled_channel`, so a new channel fails type checking until it is decided. A result dropped for a lost lease
  sends nothing; the replica that holds the lease announces it.
- **Latency after commit.** `complete` returns the `received_at` of each delivery it marked `sent` (the row, or a
  digest's members). The worker calls `record_latency(channel, received, now)` after the transaction commits, for
  every channel, so `end_to_end_latency_seconds` includes the commit that sends the UI notification.
- **Buckets.** 0.005, 0.01 and 0.025 s are added to the histogram's explicit buckets; idle p50 is ~30 ms, below the
  old 50 ms floor.

## Options

| | Exhaustive match on channel in `complete` (chosen) | `on_sent(session, job)` on `ChannelAdapter` | Flag on `Sent` |
|---|---|---|---|
| Type safety | `assert_never` covers every `Channel` | Protocol forces every adapter to implement it | A bool any adapter can set; nothing checks it per channel |
| Plumbing | None | `complete` needs the adapters; adapters get a session | `Sent` grows a field every adapter must think about |
| Where UI knowledge lives | Stage, next to `is_throttled_channel` | UI adapter | UI adapter |

| | Slot-based claims (chosen) | Semaphore over a larger claim | Keep the batch barrier |
|---|---|---|---|
| Pickup of a mid-batch delivery | Next freed slot or wake | Same | After the slowest send |
| Lease safety (ADR-0084) | No claimed row waits | Rows wait with the lease running | No claimed row waits |
| Effort | Loop rewrite | Lease must grow with the batch | None |

## Rationale

- The UI delivery row is the notification, so announcing it in the transaction that records it is the point SPEC
  §5.3 already named ("once it has recorded the delivery"), and it removes one pool checkout per UI delivery.
- Claiming per free slot removes the batch barrier without letting a claimed row wait, which a semaphore over a
  bigger claim would reintroduce.
