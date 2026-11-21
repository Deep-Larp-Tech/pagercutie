# Delivery implementation plan

Status: implemented on `t3/plan-delivery-pipeline` (chunks A to G); e2e delivery specs skip until rules and dedup land. Sources: SPEC.md §5.4, §5.5, §10, §13; DOMAIN.md §5, §6; REQUIREMENTS.md `DEL-1` to `DEL-6`,
`NFR-3`; ADR-0008, ADR-0013, ADR-0027, ADR-0045, ADR-0073.

"The delivery stage" means the two stages that turn an alert into notifications: `pipeline/routing` (creates `pending`
deliveries in the alert's transaction) and `pipeline/dispatch` (claims, throttles, sends, retries). Both are
`NotImplementedYet` stubs today, as are the routes and services they feed (channel preferences, on-call, delivery
lists). The `dedup` stage that produces `Opened` and `Renotified` is also a stub, so routing is tested against alert
rows the tests insert, not through `process_event`.

Each chunk is one reviewable diff, built by one Sonnet subagent, and ends with `mise run lint` and
`mise run test:unit` (plus `mise run test` where the chunk has integration tests) passing. Chunks in the same wave
touch disjoint files and run in parallel, each in its own worktree. The next wave starts after the previous wave is
reviewed and merged.

## 1. What exists

| Piece | State |
|---|---|
| `routing.route(session, outcome) -> list[UUID]` | Signature and docstring only |
| `dispatch.claim_due`, `send`, `complete`; `DeliveryJob`, `Sent`, `SendFailed`, `Throttled`; `ChannelAdapter` and `Throttle` Protocols | Types done, bodies stubbed |
| `dispatch.worker.run(stopping)` | Logs and waits; registered in `main.WORKERS` |
| `Delivery` model | No `lease_until` (SPEC §10 needs it), no `traceparent` (SPEC §13 needs it) |
| `NotifyChannel.DELIVERIES_PENDING` | Defined, never sent or listened to |
| `ChannelPreferences`, `Rotation`, `RotationMember` | Models and DTOs exist; `get/set_channel_preferences` (users, teams) and `GET /teams/{id}/on-call` are stubs |
| `GET /me/messages` | Done (`alerts.service.list_user_deliveries`) |
| `GET /deliveries`, `GET /alerts/{id}/deliveries` | `501` stubs |
| `{{field}}` template rendering | None; the executor needs it too (SPEC §11.2) |
| Redis client, SMTP client, Mailpit | None: no `redis` or `aiosmtplib` dependency, no Mailpit service in `compose.yaml` |

## 2. Decisions to confirm

Each is my default; overrule any and the affected chunk changes as noted.

| # | Question | Options | Recommendation |
|---|---|---|---|
| 1 | Digest for throttled deliveries (SPEC §9: "grouped into a digest instead of being dropped") | (a) Throttled rows stay `pending` with `retry_at` at the next token; when more than one due row exists for the same recipient and channel, one digest message replaces them. Needs a nullable `digest_id` column. (b) Separate `digests` table and a second loop. (c) Delay only, no digest. | (a). One table, one loop, `DEL-6` status stays per recipient and channel. (c) breaks the spec sentence; (b) adds a table for no extra behaviour. Affects chunk 1 and C. |
| 2 | Retry policy | (a) Unlimited retries, backoff `min(2^attempts, 300)` s. (b) Cap at N attempts, then terminal `failed`. | (a) for transient errors (`DEL-5`: no alert lost). Permanent errors (user has no phone or email) become `failed` with `retry_at` null and are not retried. |
| 3 | Throttling scope | Every channel, or external channels only | External channels only (email, SMS, phone). The UI channel is a feed row, and throttling it hides alerts from the live feed. Defaults: capacity 5, refill 1 token per 12 s, in `Settings`. |
| 4 | Redis outage | Fail open vs fail closed | Fail open, as SPEC §5.2 states. No decision needed; listed so the test exists. |
| 5 | When preference windows are evaluated | At routing time or at send time | Routing time (SPEC §10: "resolved when ingest creates the deliveries"). A retry keeps its channel. |
| 6 | Users who receive an alert twice (a `user` recipient who is also in a `team` recipient) | One delivery per user and channel, or one per recipient entry | One per user and channel, per notification. |
| 7 | Soft-deleted users and recipients without a rotation | Fail the alert, or skip | Skip with a `routing.skipped` warn log. An alert never fails because of its recipients. |
| 8 | A routed alert resolves nobody (every recipient skipped) | Nothing, or a UI delivery to the team's leads | Nothing. The alert is still in the team feed (`UI-1`). |
| 9 | Dispatch loop dependencies | Module globals, or a `DispatchContext` dataclass passed to `worker.run` | The dataclass. `main.WORKERS` becomes a function of the app's sessionmaker, Redis client and settings. Stays a typed constructor, no globals. |
| 10 | Email address and phone for the demo | Real SMTP to Mailpit, or log only | SMTP to Mailpit as SPEC §10 says; adds `aiosmtplib` and a `mailpit` service to compose. |

New ADRs (next free numbers at implementation time, each with a row in `docs/decisions/README.md`): digest on the
delivery table (1), retry policy and permanent failures (2), throttle scope (3), `DispatchContext` and worker
construction (9), SMTP through Mailpit with `aiosmtplib` (10).

## 3. Waves and dependencies

```
Wave 1 (parallel):  A  pure logic            B  schema + infra
Wave 2 (parallel):  C  routing               D  dispatch core         E  channel adapters      F  read API + prefs + on-call
Wave 3:             G  wiring, e2e, docs
```

| Chunk | Depends on | Touches | Does not touch |
|---|---|---|---|
| A | none | `core/templates.py`, `preferences/resolution.py`, `teams/rotation.py`, unit and property tests | models, pipeline |
| B | none | `alerts/models.py`, migration, `core/settings.py`, `pyproject.toml`, `compose.yaml`, `alerts/schemas.py` (`DeliveryStatus` if decision 1 adds a value) | stage code |
| C | A, B | `pipeline/routing/`, `tests/integration/pipeline/test_routing.py` | `dispatch/` |
| D | A, B | `pipeline/dispatch/stage.py`, `worker.py`, `throttle.py` | `routing/`, channel adapters |
| E | B | `pipeline/dispatch/channels/` | `dispatch/stage.py` |
| F | A, B | `users/service.py`, `teams/service.py`, `teams/router.py`, `alerts/service.py`, `alerts/router.py` | `pipeline/` |
| G | C, D, E, F | `main.py`, `pipeline/adapters.py` if needed, `e2e/`, docs, `contract/` | |

`pipeline/dispatch/channels/` is inside the `dispatch` package, so it respects the import-linter contracts. Add every
new module to the `banned-api` list in `pyproject.toml` only where it is a `models` module (none are new).

## 4. Chunks

### Chunk A: pure logic (no database)

Agent brief: implement three side-effect-free modules with unit and Hypothesis tests. No `Any`, `cast` or
`type: ignore`.

1. `core/templates.py`: `render(template: str, payload: Mapping[str, JsonValue]) -> str`. Accepts `{{workflowId}}`
   (payload lookup) and `{{payload.workflowId}}`, using `core.payload.field_value`. Missing field renders as empty
   string. Shared with the executor (SPEC §11.2); keep it generic. Plus `render_message(alert, channel) -> str`
   building the channel text: SMS and phone short (title only, 160 characters), email subject and body, UI title and
   body. A discriminated `match` on `Channel` ending in `assert_never`.
2. `preferences/resolution.py`: `resolve_channels(prefs: ChannelPreferences, severity: Severity, now: datetime,
   timezone: str) -> list[Channel]`. First rule with `min_severity <= severity` (via `SEVERITY_ORDER`) whose `window`
   contains `now` in `timezone` wins; windows with `end < start` cross midnight; `days` is checked on the day the
   window started. No match returns `[]` (UI only). Cases: Anna's two rules from DOMAIN.md §5, midnight crossing,
   DST transitions in `Europe/Prague`, a window start equal to end (decide: empty, document it), `now` exactly on
   `start` (inclusive) and on `end` (exclusive).
3. `teams/rotation.py`: `on_call_at(rotation: Rotation, now: datetime) -> OnCall` where `OnCall` is a frozen
   dataclass `(user_id, until)`, `None` when the rotation has no members. `members[0]` is on call in the week
   containing `started_at`; handoff at every `handoff_day` + `handoff_time` in the rotation's time zone, wrapping
   around. Property tests: result is always a member; `until` is after `now`; `on_call_at(now)` equals
   `on_call_at(until - 1 µs)`; the user changes at `until`; one full cycle returns to the start.

Tests: `tests/unit/core/test_templates.py`, `tests/unit/preferences/test_resolution.py`,
`tests/unit/teams/test_rotation.py`, `tests/property/test_rotation.py`. Done when `mise run lint` and
`mise run test:unit` pass.

### Chunk B: schema and infrastructure

Agent brief: additive changes only.

1. `Delivery` model: add `lease_until` (timestamptz, nullable), `traceparent` (text, nullable), and `digest_id`
   (UUID, nullable, FK to `deliveries.id`, if decision 1 is (a)). Replace `ix_deliveries_retry_at` with a partial
   index serving the claim query: `(retry_at) WHERE status IN ('pending','failed')`. Generate the migration with
   `mise run migration -- "delivery lease and digest"`, read it, run `mise run migrate`, and extend
   `tests/integration/test_migrations.py` if it lists columns.
2. `Settings`: `smtp_host`, `smtp_port`, `smtp_from` (defaults point at the compose Mailpit), `throttle_capacity`,
   `throttle_refill_seconds`, `delivery_lease_seconds` (default 30), `delivery_batch_size`.
3. Dependencies: `redis` and `aiosmtplib` in `pyproject.toml` (`uv lock`).
4. `compose.yaml`: a `mailpit` service (SMTP on 1025, UI on 8025) and the backend's `APP_SMTP_HOST`. Document the UI
   port in README.
5. If decision 1 adds a value to `DeliveryStatus`, run `mise run api` and commit the regenerated `contract/` and
   `frontend/src/api/generated/`; fix what `tsc` reports.

Done when `mise run lint`, `mise run test` and `mise run contract:check` pass.

### Chunk C: routing stage

Agent brief: implement `routing.route` per its docstring and SPEC §10, with the helpers from chunk A.

1. Resolve recipients: `user` (skip soft-deleted), `team` (all `lead` and `member` users, via `Membership`), `on_call`
   (load the team's `Rotation` with `selectinload`, call `on_call_at`; no rotation means skip). Deduplicate users
   across recipient entries (decision 6).
2. Channels per user: `rule.routing.channels` if set, otherwise `resolve_channels` with the preferences of the
   recipient's origin (user recipient: the user's; team and `on_call` recipient: the team's, per DOMAIN.md §5),
   using `match.event.received_at` as `now` and the user's time zone. The UI channel is always added.
3. Message: `render_message(channel, alert.title, alert.body)` from the alert row the dedup stage inserted in the
   same transaction; routing renders no templates and takes the alert's `severity` from that row too.
4. Insert with `INSERT … ON CONFLICT (id) DO NOTHING` and
   `id = uuid5(NAMESPACE, f"{alert_id}:{user_id}:{channel}:{seq}")`, where `seq` is 1 for `Opened` and
   `notification_seq` for `Renotified`. Store `traceparent` from the current span. Return only the IDs actually
   inserted.
5. `SELECT pg_notify('deliveries_pending', '')` in the same transaction when any row was inserted
   (`NotifyChannel.DELIVERIES_PENDING`). Routing sends no `alert_changed`; the dedup stage owns it.
6. Match over `Opened | Renotified` ends in `assert_never`.

Tests (`tests/integration/pipeline/test_routing.py`, real Postgres via the existing fixtures): one case per recipient
type; `routing.channels` override; Anna's window at 07:59 and 08:00 in her time zone; Settlements on-call gets phone
and SMS (acceptance scenario, ADR-0021); routing the same `Opened` twice inserts nothing new; `Renotified` seq 2
inserts a second set; soft-deleted user skipped; user in two recipient entries gets one row per channel; a
transaction that rolls back sends no notification. Done when `mise run lint` (import-linter included) and
`mise run test` pass.

### Chunk D: dispatch core

Agent brief: implement `claim_due`, `send`, `complete`, the Redis `Throttle` and the loop, keeping the existing
Protocols and result types.

1. `claim_due`: one statement, `SELECT … WHERE (status = 'pending' OR (status = 'failed' AND retry_at <= now))
   AND (lease_until IS NULL OR lease_until < now) AND (retry_at IS NULL OR retry_at <= now) ORDER BY created_at LIMIT n
   FOR UPDATE SKIP LOCKED`, set `lease_until = now + delivery_lease_seconds`, commit, return `DeliveryJob`s.
2. `send`: for external channels, `throttle.allow(user_id)`; empty bucket returns `Throttled`. Otherwise
   `adapters[job.channel].send(job)`. Adapter exceptions become `SendFailed` (the Protocol says adapters return
   failures, but a bug must not kill the loop). A channel with no adapter is a startup error, checked when the
   `DispatchContext` is built.
3. `complete`: `Sent` sets `status = sent`, `sent_at`, `attempts + 1`, clears the lease, records
   `end_to_end_latency_seconds` (`now - received_at`, SPEC §13) and `deliveries_total{channel,status}`.
   `SendFailed` sets `failed`, `attempts + 1`, `last_error`, `retry_at` by decision 2 and increments
   `delivery_retries_total`; permanent errors leave `retry_at` null. `Throttled` leaves `pending`, sets `retry_at` to
   the next token, and (decision 1a) when several due rows share a recipient and channel, merges them into one
   digest delivery row and points the originals' `digest_id` at it. The update checks `lease_until` still belongs to
   this claim, so a replica whose lease expired cannot overwrite the replica that took over.
4. `throttle.py`: `RedisThrottle(redis, capacity, refill_seconds)` implementing `Throttle`, one Lua script
   (`throttle:{user_id}`, SPEC §5.2), returning `True` on any `RedisError` (decision 4). Add `FakeThrottle` in the
   tests only.
5. `worker.run`: `DispatchContext(sessionmaker, adapters, throttle, settings, wake: asyncio.Event)`. Loop: claim,
   send concurrently (bounded `asyncio.gather`), complete each in its own transaction, repeat while a full batch came
   back; otherwise wait for `wake` or one second. A failed iteration logs `dispatch.failed` and continues, so one
   bad row never stops delivery. The send span links to the ingest trace through the stored `traceparent`.

Tests: unit tests with fakes for `send` (throttled, adapter raises, UI channel skips throttling); integration tests
(`tests/integration/pipeline/test_dispatch.py`) for two concurrent claimers never getting the same row, an expired
lease being re-claimed, a late `complete` from the old claimant being ignored, backoff values, permanent failure, and
the digest merge; Redis tests against a testcontainers Redis for the Lua bucket. Done when `mise run lint` and
`mise run test` pass.

### Chunk E: channel adapters

Agent brief: four `ChannelAdapter` implementations in `pipeline/dispatch/channels/`, one module each, plus a
`build_adapters(settings, sessionmaker) -> Mapping[Channel, ChannelAdapter]` that covers every `Channel` member
(exhaustive, so a new channel fails type checking).

| Channel | Behaviour |
|---|---|
| Email | `aiosmtplib` to `smtp_host`; recipient address from `users.email`; SMTP 4xx and connection errors are `SendFailed` (retried), 5xx are permanent |
| SMS | Simulated: requires `users.phone`, else a permanent failure; the delivery row is the record the drawer shows (DEL-4) |
| Phone | Same as SMS |
| UI | `pg_notify('alert_changed', …)` so the SSE feed shows the delivery; always succeeds |

The adapter loads the user row itself (one query per send), so `DeliveryJob` keeps its current fields. Tests: unit
tests with a fake SMTP server (`aiosmtpd` as a dev dependency) for success, 4xx and 5xx; missing phone; and an
integration test that the UI adapter's `NOTIFY` reaches a listener. Done when `mise run lint` and
`mise run test:unit` pass.

### Chunk F: read API, preferences and on-call

Agent brief: the services and routes that routing and the drawer depend on. Routers stay free of model imports.

1. `users.service.get/set_channel_preferences` and `teams.service` equivalents (`GET`/`PUT
   /teams/{id}/channel-preferences`, lead or admin writes). `PUT` replaces the value object; validation stays in
   `ChannelPreferences`.
2. `GET /teams/{team_id}/on-call` through `teams.rotation.on_call_at`; `user: null` and `until: null` without a
   rotation.
3. `GET /deliveries` (visibility per ADR-0073: the user's teams' alerts, escalated alerts, personal-rule alerts;
   admin sees all; `channel` and `status` filters; newest first) and `GET /alerts/{id}/deliveries` (404 when the user
   cannot see the alert). Reuse the visibility predicate the alerts feed uses; if none exists yet, put it in
   `alerts/service.py` once.
4. Remove the matching `NotImplementedYet` calls. No contract change is expected (routes and DTOs exist); run
   `mise run contract:check` to confirm.

Tests: integration tests per route for success, `401`, `403`/`404` visibility, filters and pagination; the contract
test stops skipping these routes. Done when `mise run lint`, `mise run test` and `mise run contract:check` pass.

### Chunk G: wiring, end-to-end, docs

Agent brief:

1. `main.py`: create the Redis client and `DispatchContext`; build the dispatch `Worker` from them in `create_app`
   (replaces the module-level `WORKERS` entry); register `DELIVERIES_PENDING: wake.set` on the listener. Close the
   Redis client in the lifespan. Share the client with the future dedup `WindowStore` through `app.state`.
2. `e2e/`: a Playwright spec for the happy path (event in, delivery visible in the drawer and in Mailpit), the
   Settlements on-call scenario, and a retry scenario that stops Mailpit and starts it again. The specs skip while the
   dependent stages answer `501`, like the contract test.
3. Docs: SPEC §10 (digest, retry cap, throttle scope, permanent failures), DOMAIN.md §6 delivery lifecycle,
   README (Mailpit URL), ADRs from section 2, `docs/decisions/README.md` rows.
4. `mise run api` if any DTO changed in chunks B or F; commit generated files with the change.

Done when `mise run lint`, `mise run test`, `mise run contract:check`, `mise run e2e` and
`cd frontend && pnpm lint && pnpm build` pass.

## 5. Acceptance scenarios

These come from the brief (ADR-0021) and run end to end in chunk G, and as integration tests in C and D.

- Settlements: `WORKFLOW_FAILED` in `prod` creates phone and SMS deliveries for the on-call person and a UI row.
- Anna: critical from `payments-api` creates an email at 07:59 local time, an SMS at 08:00, and an email again at 20:00.
- Retry: Mailpit down, delivery `failed` with growing `retry_at`; Mailpit up, delivery `sent`, no duplicate email.
- Replica death: a claimed delivery whose replica dies is sent by another replica after the lease expires.
- Burst: 50 deliveries for one user inside a minute produce at most `throttle_capacity` immediate messages and one
  digest.
- `NFR-3`: `end_to_end_latency_seconds` p50 and p99 appear in Grafana for a 100-event run.

## 6. Risks

| Risk | Mitigation |
|---|---|
| `dedup.record` and the rule loader are stubs, so no test reaches routing through `process_event` | Chunk C inserts alert rows directly, like `tests/integration/alerts/test_messages.py`; add one `process_event` test once dedup lands |
| Two chunks edit `pyproject.toml` or `main.py` | Only B edits `pyproject.toml`, and only G edits `main.py` |
| A subagent weakens typing to pass checks | Each brief repeats the rule; I review every diff for `Any`, `cast`, `type: ignore` before merging |
| Agents add features beyond the brief | Each brief lists files it may touch; anything else is reported, not changed |
