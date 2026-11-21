# ADR-0105: Escalation runs in the step's transaction through a shared recipients module

- **ID:** ADR-0105
- **Timestamp:** 2026-11-21T18:00+01:00
- **Status:** Accepted
- **See:** SPEC §5.5, §11.4 step 5, RUN-3, ADR-0045, `backend/src/pagercutie/pipeline/recipients.py`

## Decision

An approved `escalate` step yields `EscalationDue(team)`. `complete_step` resolves the slug to a team, writes the
step's outcome and, only when that conditional write succeeded, in the same transaction:

- appends the team to `alerts.escalated_team_ids` unless it is there already;
- inserts `pending` deliveries for the team's leads and members, with the team's channel preferences for the alert's
  severity at the escalation time, plus the UI channel (`received_at` is the escalation time);
- audits `alert.escalated` (actor null, `approved_by` in `data`) and sends `NOTIFY alert_changed` when the team was
  added; the insert sends `deliveries_pending`.

A slug that names no team fails the step. Delivery IDs are `uuid5` of `{alert}:{user}:{channel}:escalation:{team}`, so
a retried step inserts nothing new and escalation deliveries never collide with routing's `{alert}:{user}:{channel}:{seq}`.

Recipient resolution, channel choice and the delivery insert move from `pipeline/routing/stage.py` to
`pipeline/recipients.py`, a pipeline module that imports no stage. `routing.route` and the executor's escalation both
call it.

| Option | Tradeoff |
|---|---|
| A message (`Escalated`) handled by the orchestrator or a worker | Keeps routing the only writer of deliveries; but the orchestrator runs only in the ingest request and the executor's loop may not import routing, so the hand-off needs a table and a second loop, and the escalation no longer commits with the step |
| **Shared non-stage module `pipeline/recipients.py`** (chosen) | One implementation of recipient resolution and deterministic IDs; atomic with the step; passes the import-linter contracts unchanged, since they name only the six stage packages. Moves code out of the routing stage that ADR-0045 gave it |
| Routing behind a Protocol passed into the executor (`Integrations`) | Keeps the code in routing and follows ADR-0013; `complete_step` would take one more dependency wired in `main.py`, and routing would expose a second entrypoint only the executor calls |

## Rationale

- SPEC §11.4 step 5 asks for the team to be added and its deliveries created on approval; doing both in the step's
  transaction means an approved escalation is never half done.
- Reusing routing's resolution keeps one rule for who a `team` recipient reaches (leads and members, DEL-2).
