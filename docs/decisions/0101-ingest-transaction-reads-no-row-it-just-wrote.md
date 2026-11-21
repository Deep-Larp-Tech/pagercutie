# ADR-0101: The ingest transaction reads no row it just wrote

- **ID:** ADR-0101
- **Timestamp:** 2026-11-21T12:00+01:00
- **Status:** Accepted
- **See:** ADR-0099, ADR-0045, SPEC §5.3, §5.5, `backend/src/pagercutie/pipeline/messages.py`,
  `backend/src/pagercutie/pipeline/orchestrator.py`

## Context

Tempo traces of an opened alert (team recipient, linked runbook) showed 15 sequential statements in the ingest
transaction. Under load each one costs about 7 ms of event-loop wait, so the transaction took about 110 ms p50 of
the 690 ms end-to-end latency. Four of them re-read or re-announced what the transaction already had in memory:
routing's `SELECT alerts.*`, the executor's `SELECT alerts.team_id`, a separate autoflushed audit `INSERT`, and the
executor's `NOTIFY alert_changed alert.updated`.

## Decision

- **Messages.** `Opened` and `Renotified` gain `content: AlertContent` (severity, title, body), filled from the
  upsert's `RETURNING`. A renotification leaves those columns alone, so they are the existing row's values. `Opened`
  gains `team_id` (the rule owner's team, null for a personal rule), which the insert wrote. Routing and
  `start_run` read no alert row. These messages are internal; no API contract changes.
- **Audit batching.** The orchestrator runs the transaction under `no_autoflush`. The stages add only audit
  entries to the session and never read them back, so all entries go out in one `INSERT` at commit.
- **No `alert.updated` from `start_run`** (amends ADR-0099). `start_run` runs only in the transaction that
  inserted the alert, which also sends `alert.created`. Both notifications are delivered at commit, so no alert
  detail can hold a view from before the run existed; the detail stream reloads the run on any event for the alert,
  and `feed_events` keeps `alert.created` when a batch holds both types.

Statements for the measured case: 15 before, 11 after (test
`test_an_opened_alert_is_recorded_routed_and_run_without_rereading_its_rows`).

## Options

| | Carry the values on the messages (chosen) | Load the alert into the session in dedup | Keep the reads |
|---|---|---|---|
| Statements saved | 2 | 1 (the ORM upsert still needs one statement; routing hits the identity map) | 0 |
| Stage coupling | Messages only (SPEC §5.5) | Routing depends on session state dedup left behind | None |
| Type safety | Typed message fields | ORM instance, typed | Unchanged |

| | `no_autoflush` over the transaction (chosen) | Flush audit entries explicitly at the end | Autoflush |
|---|---|---|---|
| Audit `INSERT`s | 1 at commit | 1 | One per later ORM query (2 here) |
| Risk | A stage that later reads its own pending rows must flush first | Same, plus a call to forget | None |

## Rationale

- The upsert already returns a row, so adding three columns costs nothing and keeps the stages talking through
  messages only.
- The removed `alert.updated` duplicated an `alert.created` committed in the same transaction for every consumer.
