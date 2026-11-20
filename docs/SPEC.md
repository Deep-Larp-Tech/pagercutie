# PagerCutie — Specification

PagerCutie is a notification router and policy evaluator. It ingests events from many sources in arbitrary,
runtime-defined formats, evaluates team-defined rules against them, and delivers alerts to the right people
on the channels they prefer, together with the runbook steps needed to resolve them.

It is multi-user, multi-team and multi-source.

This document describes **how** PagerCutie works. **What** it must do is listed in
[REQUIREMENTS.md](REQUIREMENTS.md); requirement IDs (e.g. `RUL-1`) refer to that file.

---

## 1. Problem and goals

Systems produce errors, warnings and business events (a failed workflow, a breached threshold, a rejected
message). Today these signals are scattered across logs, dashboards and mailboxes, so the right people either
find out too late or receive so many alerts that they stop reading them.

PagerCutie MUST get **the right alert to the right people, on the channel they prefer**, and help them
**resolve it by following the team's runbooks**.

Guiding qualities:

| Quality     | Meaning                                                                    |
|-------------|----------------------------------------------------------------------------|
| Flexibility | Easy to adopt for any team or system.                                      |
| Scalability | A high volume of messages and alerts must not degrade service performance. |
| UX          | Usable by engineers, on-call support, and non-engineers alike.             |

## 2. Glossary

| Term            | Definition                                                                                              |
|-----------------|---------------------------------------------------------------------------------------------------------|
| **Source**      | An origin of events: a message broker topic, an HTTP/webhook endpoint, a tailed log file, a polled API. |
| **Event**       | A single raw message received from a source.                                                            |
| **Envelope**    | The internal wrapper around an event: ID, source, schema, timestamps, raw payload (§4.2).               |
| **Schema**      | A runtime-defined description of an event's structure, types and value constraints (JSON Schema).      |
| **Rule**        | A condition over event fields plus dedup, routing, presentation and runbook settings.                   |
| **Match**       | The fact that one event satisfied one rule. Input to deduplication.                                     |
| **Fingerprint** | Hash of a rule's dedup fields taken from the event. Matches with the same rule and fingerprint are the same alert. |
| **Alert**       | Created from the first match of a fingerprint. Has a lifecycle: open → acknowledged → resolved.         |
| **Delivery**    | One attempt to notify one recipient about one alert on one channel. Has a status.                       |
| **User**        | A person who can receive alerts.                                                                         |
| **Team**        | A named group of users. Teams own rules.                                                                 |
| **Recipient**   | A user or team that an alert is routed to.                                                               |
| **Channel**     | A delivery medium: Email, SMS, Phone call, UI.                                                           |
| **Runbook**     | Instructions attached to a rule, schema or alert type describing how to resolve an alert.                |
| **Step**        | One item of a runbook: an action, a check or a manual instruction, optionally guarded by `if`.          |
| **Action**      | What a step does: retry workflow, restart service, call webhook, escalate, manual, …                    |
| **Runbook run** | The execution of a runbook for one alert: the state of each step, approvals and results.                |
| **On-call**     | The team member currently responsible for receiving the team's alerts, from a rotation.                  |

## 3. Architecture

### 3.1 Topology

```mermaid
architecture-beta
    service producers(internet)[Event producers]
    service browser(internet)[Browser]

    group stack(cloud)[PagerCutie docker compose]

    service ingest(server)[Ingest] in stack
    service events(disk)[Topic events] in stack
    service evaluator(server)[Evaluator] in stack
    service matches(disk)[Topic matches] in stack
    service dedup(server)[Dedup] in stack
    service deliveries(disk)[Topic deliveries] in stack
    service dispatcher(server)[Dispatcher] in stack
    service postgres(database)[Postgres] in stack
    service api(server)[API] in stack
    service caddy(server)[Frontend Caddy] in stack
    service mailpit(server)[Mailpit mock SMTP] in stack
    service lgtm(server)[Grafana LGTM] in stack

    producers:R --> L:ingest
    ingest:B --> T:events
    events:R --> L:evaluator
    evaluator:B --> T:matches
    matches:R --> L:dedup
    dedup:B --> T:deliveries
    deliveries:R --> L:dispatcher
    dispatcher:R --> L:mailpit
    dedup:R --> L:postgres
    dispatcher:T --> B:postgres
    api:B <--> T:postgres
    caddy:B --> T:api
    browser:R --> L:caddy
    api:R --> L:lgtm
```

Reading the diagram:

- The **hot path** runs top-left to bottom-right: producers → ingest → `events` → evaluator → `matches` →
  dedup → `deliveries` → dispatcher → channels. All three topics live in one **Redpanda** broker (§5).
- **Postgres** holds the low-volume state: rules, schemas, alerts, deliveries, audit log. Evaluator and
  ingest also read rules and schemas from it into memory (edges not drawn).
- **Every process** exports OpenTelemetry data to Grafana LGTM; only the API edge is drawn.
- SMS and phone are simulated: the dispatcher writes them to Postgres, and the UI shows them in a "fake phone"
  panel. Email goes to Mailpit, which has its own web inbox.

### 3.2 Process roles

The backend is **one codebase and one Docker image** (a "modular monolith"). It starts in different roles:

| Role         | Does                                                                          | State            | Scales by                    |
|--------------|-------------------------------------------------------------------------------|------------------|------------------------------|
| `ingest`     | Source adapters → schema resolution and validation → produce to `events`      | None             | Replicas behind Caddy        |
| `evaluator`  | Consume `events` → evaluate rules → produce one message per match to `matches` | Rules in memory  | Replicas, ≤ partitions       |
| `dedup`      | Consume `matches` → dedup windows → upsert alert in Postgres → produce to `deliveries` | Dedup windows in memory, per partition | Replicas, ≤ partitions |
| `dispatcher` | Consume `deliveries` → throttle per recipient → send via channel adapter → retries | Throttle counters in memory, per partition | Replicas, ≤ partitions |
| `executor`   | Run runbook steps from the Postgres job table, wait for approvals (§11.3)     | None             | Replicas (`SKIP LOCKED`)     |
| `api`        | REST API for the UI, SSE live feed, auth, audit log, action approvals         | None             | Replicas behind Caddy        |

Run modes:

```
backend --role=ingest|evaluator|dedup|dispatcher|executor|api   # production / demo: one role per container
backend --role=worker                                           # evaluator + dedup + dispatcher + executor
backend --role=all                                     # local dev: everything in one process, in-memory queue
```

All roles talk to the queue through one `Queue` interface with two implementations: Redpanda and in-memory.
`--role=all` therefore needs only Postgres, and runs the same code as the distributed setup.

### 3.3 Technology

| Concern          | Choice                                                                                  |
|------------------|-----------------------------------------------------------------------------------------|
| Backend          | Python 3.14, FastAPI, SQLAlchemy (async) + Alembic, Pydantic                            |
| Broker           | Redpanda (Kafka API), Python client `confluent-kafka`                                   |
| Database         | PostgreSQL 18 (`jsonb` for event payloads, rule ASTs and schemas)                       |
| Event validation | JSON Schema 2020-12, validated with `jsonschema-rs` (same Rust engine as the later Rust port) |
| Frontend         | React 19, TanStack Router + Query, Tailwind, `orval`-generated API client, served by Caddy |
| Observability    | OpenTelemetry → `grafana/otel-lgtm` (Grafana, Prometheus, Tempo, Loki)                  |
| Email mock       | Mailpit                                                                                 |
| Later            | Hot paths ported to Rust: first the evaluator as a PyO3 module, then whole roles        |

## 4. Contracts

All contracts live in `contract/`. Generated code is never edited by hand. CI regenerates every artifact and
fails if the committed file differs (same pattern as the existing `mise run contract:check`).

| Contract             | Between                              | Format                    | File                                  |
|----------------------|--------------------------------------|---------------------------|---------------------------------------|
| Broker messages      | ingest → evaluator → dedup → dispatcher | Protobuf (buf module)   | `contract/proto/pagercutie/v1/messages.proto` |
| Rule AST, runbooks   | frontend builder ↔ API ↔ evaluator / executor | JSON Schema 2020-12, generated from Pydantic | `contract/rule.schema.json`, `contract/runbook.schema.json` |
| Evaluator test cases | Python evaluator ↔ Rust evaluator    | JSON fixtures             | `contract/rule-tests/*.json`          |
| Management API       | frontend ↔ API                       | OpenAPI 3.1               | `contract/openapi.json`               |
| User event schemas   | users → ingest                       | JSON Schema, **stored as data** in Postgres | none (runtime data) |

### 4.1 Compatibility rules

- Changes MUST be **additive**: add fields, never rename, retype or reuse them. Consumers ignore unknown fields.
- Deploy **consumers before producers** when a message gains a field.
- Protobuf: never change or reuse a field number; delete a field by marking it `reserved`.

### 4.2 Broker messages: `contract/proto/pagercutie/v1/messages.proto`

```proto
syntax = "proto3";
package pagercutie.v1;

// Topic `events`, produced by ingest.
message Event {
  string event_id       = 1;  // UUIDv7, assigned by ingest
  string source         = 2;  // source instance ID from config, e.g. "payments-webhook"
  string schema_id      = 3;  // resolved by ingest (§7)
  int64  received_at_ms = 4;  // ingest time; basis for end-to-end latency
  bytes  payload        = 5;  // event body as JSON, whatever the original wire format was
  string severity       = 6;  // normalised: "debug" | "info" | "warn" | "error" | "critical" (§8.1)
}

// Topic `matches`, produced by the evaluator. One per (event, matching rule).
message Match {
  string event_id       = 1;
  string rule_id        = 2;
  string fingerprint    = 3;  // hex SHA-256 of the rule's dedup field values (§9)
  int64  received_at_ms = 4;  // copied from Event
  bytes  payload        = 5;  // copied from Event, for templating
}

// Topic `deliveries`, produced by dedup.
message Delivery {
  string delivery_id    = 1;  // deterministic: hash(alert_id, recipient_id, channel, notification_seq)
  string alert_id       = 2;
  string recipient_id   = 3;
  string channel        = 4;  // "email" | "sms" | "phone" | "ui"
  int64  received_at_ms = 5;  // copied from the first Match
}
```

- `payload` is always **JSON** inside the pipeline. A source that receives protobuf (or anything else) decodes
  it to JSON in its adapter, so evaluator and dedup deal with one format only.
- Trace context is carried in the Kafka message **headers** (W3C `traceparent`), not in the messages, following
  OpenTelemetry's messaging conventions.
- `buf` (installed via mise) lints the module, checks breaking changes against `main` and generates Python
  code plus `.pyi` stubs (`protocolbuffers/python` and `pyi` plugins) into `backend/src/pagercutie/v1/`,
  imported as `pagercutie.v1.messages_pb2`. Tasks: `mise run proto:lint|proto:gen|proto:breaking|proto:check`.
  Rust code is generated from the same file with `prost`.

### 4.3 Rule AST: `contract/rule.schema.json`

**Source of truth: Pydantic models in the backend.** Each node type is one model with a `Literal` tag, and
all of them form a **discriminated union** on the key `op`. From that single definition:

- `contract/rule.schema.json` (the whole rule document, `RuleCreate`, with `Condition` in its `$defs`) and
  `contract/runbook.schema.json` (the structured YAML runbook) are exported by `mise run contract`, for the
  Rust port (types generated with `typify`) and for tools;
- FastAPI includes the models in `contract/openapi.json`, so `orval` generates the TypeScript union types and
  zod validators for the visual builder.

The API validates every rule before saving it, so the evaluator never sees an invalid AST.

```python
type Scalar = str | int | float | bool | None
type FieldPath = Annotated[str, Field(pattern=r"^[A-Za-z_]\w*(\.\w+)*$")]

class And(BaseModel):
    op: Literal["and"]
    args: list[Condition] = Field(min_length=1)

class Or(BaseModel):
    op: Literal["or"]
    args: list[Condition] = Field(min_length=1)

class Not(BaseModel):
    op: Literal["not"]
    arg: Condition

class Compare(BaseModel):
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte"]
    field: FieldPath
    value: Scalar

class In(BaseModel):
    op: Literal["in", "not_in"]
    field: FieldPath
    value: list[Scalar] = Field(min_length=1)

class Contains(BaseModel):
    op: Literal["contains"]
    field: FieldPath
    value: Scalar

class Glob(BaseModel):
    op: Literal["glob"]          # "pricing-engine-*", "trade.rejected.*"
    field: FieldPath
    value: str

class Exists(BaseModel):
    op: Literal["exists"]
    field: FieldPath

type Condition = Annotated[
    And | Or | Not | Compare | In | Contains | Glob | Exists,
    Field(discriminator="op"),
]
```

**Fields** are dot paths into the normalised event `{"source": …, "schema_id": …, "severity": …,
"payload": { … }}`, e.g. `source`, `payload.amount`, `payload.error.code`. The root is named `payload` to
match the brief's templates (`{{payload.currency}}`).

**Example:** the brief's `amount > 1,000,000` or `error.code in [TIMEOUT, REJECTED]`, critical only:

```json
{
  "op": "and",
  "args": [
    { "op": "eq", "field": "severity", "value": "critical" },
    { "op": "or", "args": [
      { "op": "gt", "field": "payload.amount", "value": 1000000 },
      { "op": "in", "field": "payload.error.code", "value": ["TIMEOUT", "REJECTED"] }
    ]}
  ]
}
```

A full **rule** wraps the condition with its other parts (§8). Example: the brief's Team Settlements rule. IDs are
shown as readable names for clarity; in the API they are UUIDs (DOMAIN.md §1), and the owner is
`{"type": "team", "team_id": …}`.

```json
{
  "id": "r-settlement-failed",
  "team_id": "settlements",
  "name": "Order settlement failed in prod",
  "enabled": true,
  "condition": { "op": "and", "args": [
    { "op": "eq", "field": "payload.type", "value": "WORKFLOW_FAILED" },
    { "op": "eq", "field": "payload.workflowName", "value": "order-settlement" },
    { "op": "eq", "field": "payload.environment", "value": "prod" }
  ]},
  "dedup": { "fields": ["payload.workflowId"], "window_s": 300 },
  "routing": { "recipients": [{ "type": "on_call", "team_id": "settlements" }], "channels": ["phone", "sms"] },
  "presentation": {
    "title": "Settlement {{payload.workflowId}} failed at {{payload.step}}",
    "body": "{{payload.error.message}}",
    "fields": ["payload.step", "payload.error.message"],
    "severity": "critical",
    "colour": "red"
  },
  "runbook_id": "settlement-timeout"
}
```

`routing.channels: null` means "use each recipient's channel preferences for this severity" (`DEL-2`).

### 4.4 Adding a variant: merge checks

New conditions (§4.3), runbook actions (§11.2) and channels are added **in Python only**: one new model in
the union, plus its handler. The type checkers then block the merge until every consumer handles it:

| Where                | Mechanism                                                         | What fails                       |
|----------------------|-------------------------------------------------------------------|----------------------------------|
| Generated files      | `contract:check` regenerates and runs `git diff --exit-code`      | The contract was not regenerated |
| Python consumers     | `match` over the union ending in `case _: assert_never(x)`       | `ty check`: variant not handled  |
| Frontend             | Handler maps declared with `satisfies Record<Condition["op"], …>` | `tsc`: missing key               |
| Evaluator test cases | A test asserting every `op` has ≥1 case in `contract/rule-tests/` | pytest                           |
| Rust (later)         | `match` on the generated enum                                     | The compiler                     |

```python
def evaluate(c: Condition, event: Event) -> bool:
    match c:
        case And(args=args): return all(evaluate(a, event) for a in args)
        case Or(args=args):  return any(evaluate(a, event) for a in args)
        case Not(arg=arg):   return not evaluate(arg, event)
        case Compare():      return compare(c, event)
        case In():           return member(c, event)
        case Contains():     return contains(c, event)
        case Glob():         return glob(c, event)
        case Exists():       return lookup(event, c.field) is not MISSING
        case _:              assert_never(c)
```

```ts
const editors = {
  and: GroupEditor, or: GroupEditor, not: NotEditor,
  eq: CompareEditor, ne: CompareEditor, gt: CompareEditor, gte: CompareEditor, lt: CompareEditor, lte: CompareEditor,
  in: InEditor, not_in: InEditor, contains: CompareEditor, glob: GlobEditor, exists: ExistsEditor,
} satisfies Record<Condition["op"], ConditionEditor>;
```

`ty` is pre-1.0: confirm that it reports a deliberately unhandled variant before relying on it. If it does
not, add pyright to `mise run lint` for this check.

### 4.5 Management API

- FastAPI generates the OpenAPI document. `mise run contract` exports it to `contract/openapi.json`.
- The frontend's API client, TypeScript types and zod schemas are generated from it with `orval`.
- Errors use one JSON error format across all endpoints.

### 4.6 No gRPC between internal services

Internal services communicate **only through the broker and Postgres**. The broker gives buffering,
durability and key-based routing (§5). Synchronous gRPC calls between services would give none of these,
and would add a call chain that has to be available end to end.

gRPC MAY still be added as an **ingest source adapter**: an external system pushing protobuf events over gRPC
is one more source type (§6), decoded to the JSON envelope like every other source.

## 5. Messaging

### 5.1 Topics

| Topic        | Producer   | Consumer group | Partition key                 | Why this key                                                         |
|--------------|------------|----------------|-------------------------------|----------------------------------------------------------------------|
| `events`     | ingest     | `evaluator`    | none (spread evenly)          | Evaluation is stateless; any worker can take any event.              |
| `matches`    | evaluator  | `dedup`        | `rule_id:fingerprint`         | Every occurrence of the same alert reaches the same dedup worker.    |
| `deliveries` | dedup      | `dispatcher`   | `recipient_id`                | Per-recipient throttling sees all deliveries for that recipient.     |
| `events-dlq` | ingest     | none (inspected manually) | none               | Events that failed schema resolution or validation.                 |

- **12 partitions** per topic, fixed from the start. Changing the count remaps keys (`hash(key) % P`) and
  resets in-memory windows.
- Dev and demo: one Redpanda node, replication factor 1. Production: 3 nodes, replication factor 3,
  `min.insync.replicas=2`. Only configuration differs.

### 5.2 Routing and affinity

Three independent mappings:

| Mapping              | Depends on                         | Changes when…                    |
|----------------------|------------------------------------|----------------------------------|
| key → partition      | `hash(key) % P`                    | the partition count changes      |
| partition → worker   | consumer group membership          | a **worker** joins or leaves     |
| partition → broker   | partition leader election          | a **broker** joins or leaves     |

Because each partition is read by exactly one worker of the group at a time, dedup windows and throttle
counters can live **in worker memory**, with no shared store on the hot path.

- **A broker leaves:** new leaders are elected for its partitions. Clients refresh metadata and continue on
  the same partitions. Keys and worker assignments do not change, so in-memory state stays valid.
- **A worker leaves:** its partitions move to other workers, which start with empty windows. Static
  membership (`group.instance.id`) gives a restarted worker the same partitions back without a rebalance.
  The Postgres upsert on open alerts (§9) catches any duplicate after a real rebalance.

### 5.3 Delivery semantics

**At-least-once** end to end, made safe by idempotent consumers:

1. A consumer processes a message, writes its results (Postgres and/or the next topic), and **only then
   commits** the offset.
2. If it crashes in between, the message is processed again. Alert upserts (by fingerprint) and delivery
   inserts (by `delivery_id`) are idempotent, so reprocessing creates no duplicates.

### 5.4 Client configuration

```python
PRODUCER = {"acks": "all", "enable.idempotence": True, "linger.ms": 1}
CONSUMER = {
    "group.instance.id": os.environ["WORKER_ID"],           # static membership
    "partition.assignment.strategy": "cooperative-sticky",
    "session.timeout.ms": 30000,
    "enable.auto.commit": False,
}
```

Every worker shuts down gracefully on `SIGTERM`: stop polling, flush in-memory counters, commit offsets, exit.

## 6. Sources

*Satisfies `ING-1`, `ING-2`.*

- Every source type implements one **source adapter** interface: receive raw input, return
  `(source_id, raw_payload)`. Adding a source type means writing one adapter.
- Adding a new **instance** of an existing type (another webhook path) is configuration only.
- Initial adapters: **HTTP webhook** and **WebSocket**. Planned: **protobuf** (over HTTP, possibly gRPC).
- Ingest replies to a webhook only after the broker confirmed the write (`acks=all`), so an accepted event is
  never lost.

## 7. Events and schemas

*Satisfies `SCH-1` – `SCH-3`.*

- Event schemas are **JSON Schema 2020-12 documents stored in Postgres**, created and changed at runtime.
  JSON Schema covers `SCH-3`: sub-schemas (`$defs` / `$ref`), types (primitive, array, object) and
  type-dependent constraints (`maxLength`, `minimum`, `minItems`, …).
- Ingest compiles each schema once and caches it; it reloads on Postgres `NOTIFY schemas_changed`.
- Events that fail validation go to `events-dlq` and increment `events_rejected_total{reason}`.
- Ingest does not store events in Postgres. The `events` topic is the raw log, with time-based retention.

## 8. Rules

*Satisfies `RUL-1` – `RUL-5`.*

| Part             | Contents                                                                    |
|------------------|-----------------------------------------------------------------------------|
| **Condition**    | AST of AND / OR / NOT groups and predicates (§4.3).                         |
| **Dedup**        | Fields forming the fingerprint, window length (§9).                         |
| **Routing**      | Recipients; channels, or `null` to use the recipients' preferences.        |
| **Presentation** | Title and body templates, included fields, severity, UI colour.             |
| **Runbook**      | Optional runbook attachment (§11).                                          |

- Rules are edited in the **visual builder**, which produces the AST directly. A textual syntax MAY be added
  later on top of the same AST.
- Rules are stored in Postgres and changed through the API (`RUL-5`). Evaluators cache all enabled rules in
  memory, compiled once to closures, and reload on `NOTIFY rules_changed`. No restart is needed.

### 8.1 Evaluator semantics

The evaluator is a pure function `(rule, event) → bool`. It is **total**: it never raises on any input.

- A predicate on a **missing field** is `false`, except `exists`.
- A predicate with a **type mismatch** (e.g. `gt` on a string field against a number) is `false`.
- `not` negates the result above, so `not(eq)` is `true` for a missing field. This is intended.
- `contains`: substring for strings, membership for arrays, `false` otherwise.
- `glob`: shell-style wildcards (`*`, `?`) on strings, `false` otherwise.
- `gt`/`gte`/`lt`/`lte` compare numbers with numbers and strings with strings (ISO timestamps sort correctly).
- **`severity` is ordered:** ingest normalises it to `debug < info < warn < error < critical` (mapping
  per source, e.g. `WARNING → warn`), so "WARN or above" is `{"op": "gte", "field": "severity",
  "value": "warn"}`.

The cases in `contract/rule-tests/*.json` (`{rule, event, expected}`) MUST pass in every evaluator
implementation, Python and Rust.

## 9. Noise reduction

*Satisfies `NOI-1`, `NOI-2`.*

- **Fingerprint:** `sha256(rule_id + values of rule.dedup.fields)`. An empty field list means one alert per
  rule per window.
- **Grouping** uses the same mechanism: the brief's "group pricing log lines into one alert per instrument
  every 5 minutes" is `"dedup": {"fields": ["payload.instrument"], "window_s": 300}`.
- **Deduplication** (dedup role): the first match of a fingerprint within `window_s` upserts an alert in
  Postgres and produces the deliveries. Later matches only increment an in-memory counter, flushed to the
  alert row every 5 s. 500 identical errors cost about two Postgres writes, not 500.
- A partial unique index on the fingerprint of **open** alerts makes the upsert idempotent and catches
  duplicates after a worker rebalance.
- **Throttling** (dispatcher role): a per-recipient token bucket in memory, possible because `deliveries` is
  keyed by `recipient_id`. Throttled deliveries are grouped into a digest instead of being dropped.

## 10. Delivery

*Satisfies `DEL-1` – `DEL-6`.*

- Every channel implements one **channel adapter** interface. Replacing a simulated provider with a real one
  touches only that adapter (`DEL-4`).

  | Channel | Adapter for the demo                                    |
  |---------|---------------------------------------------------------|
  | Email   | SMTP to Mailpit                                         |
  | SMS     | Simulated: row in Postgres, shown in the UI phone panel |
  | Phone   | Simulated: row in Postgres, shown in the UI phone panel |
  | UI      | Row in Postgres + `NOTIFY`, pushed to the browser over SSE |

- **Recipients** are users, teams, or `on_call` of a team. The on-call person comes from a simple weekly
  rotation table (`DEL-3`), resolved when dedup produces the deliveries.
- **Channel preferences** map severity to channels and MAY have a time window with a fallback (`DEL-3`), e.g.
  Anna: `critical → sms` between 08:00 and 20:00 in her time zone, otherwise `email`.
- The dispatcher inserts each delivery as `pending` (idempotent by `delivery_id`) before sending, then marks
  it `sent` or `failed` (`DEL-6`).
- **Retries:** failed deliveries get `retry_at` with exponential backoff. A retry loop in the dispatcher picks
  them up with `SELECT … FOR UPDATE SKIP LOCKED`, so a channel that is down for a long time never blocks the
  partition and no delivery is lost (`DEL-5`).

## 11. Runbooks and actions

*Satisfies `RUN-1` – `RUN-8`.*

Judges will bring runbook formats we have not seen (`RUN-8`). Design rule: **every runbook always displays
correctly, and the parts we understand become executable steps.**

### 11.1 One model, several input formats

```python
class Runbook(BaseModel):
    id: str
    title: str
    attach: Condition                 # when this runbook applies (§4.3)
    format: Literal["structured", "markdown", "text", "link"]
    original: str                     # raw input, always kept and viewable
    steps: list[Step]
```

| Input            | Parsing                                                               | Result                                   |
|------------------|-----------------------------------------------------------------------|------------------------------------------|
| Structured YAML  | Validated directly against the Pydantic `Runbook` model               | Executable steps                         |
| Markdown         | Numbered or bulleted items → `manual` steps; links detected           | A checklist, ticked off by humans        |
| Wiki / link      | Stored as a link                                                      | One `manual` step: "open the runbook"    |
| Free text, unknown | Stored as-is                                                        | One `manual` step showing the text       |

- The YAML's `matches:` block is shorthand for an `and` of `eq` conditions, converted to `attach`.
- **(optional)** An LLM proposes a structured version of a Markdown or free-text runbook. A human reviews it
  in the UI before it is saved. This also serves `UI-4` and `RUN-7`. If built, `SUB-3` requires describing
  how security and privacy were handled.

### 11.2 Steps and actions

Steps are a discriminated union on the key `action`, which is the key the brief's YAML already uses. Adding
an action follows §4.4: one model and one handler.

```python
class StepBase(BaseModel):
    check: str | None = None                                   # question shown to humans
    if_: str | StepGuard | None = Field(None, alias="if")      # guard, see §11.4
    approval: Literal["none", "required"] | None = None        # None → the action's default

class HttpGet(StepBase):       action: Literal["http_get"];       url: Templated[str]
class RetryWorkflow(StepBase): action: Literal["retry_workflow"]; workflow_id: Templated[str] = Field(alias="workflowId")
class RestartService(StepBase): action: Literal["restart_service"]; service: Templated[str]
class CallWebhook(StepBase):   action: Literal["call_webhook"];   url: Templated[str]
class OpenTicket(StepBase):    action: Literal["open_ticket"];    title: Templated[str]
class Escalate(StepBase):      action: Literal["escalate"];       team: str
class Wait(StepBase):          action: Literal["wait"];           seconds: int
class Manual(StepBase):        action: Literal["manual"];         text: str

type Step = Annotated[
    HttpGet | RetryWorkflow | RestartService | CallWebhook | OpenTicket | Escalate | Wait | Manual,
    Field(discriminator="action"),
]
```

- **Risk defaults:** every action type has a default approval. Read-only actions (`http_get`, `wait`) default
  to `none`; `restart_service`, `escalate`, `call_webhook` and failovers default to `required`; `retry_workflow`
  and `open_ticket` default to `none`. A runbook MAY make a step stricter than its default, never looser (`RUN-4`).
- **Execution:** an abstract `ActionFactory` has one method per step type and dispatches to them with an
  exhaustive `match`. The action's `run()` returns a result (`ok`, `summary`, `outputs`) that the
  runbook run applies to the step's state ([ADR-0030](decisions/0030-action-factory-and-in-memory-runbook-run.md)).
- **Templates** (`Templated[str]`) are rendered from the event when the step runs. Both `{{workflowId}}`
  (looked up in the payload) and `{{payload.workflowId}}` are accepted, because the brief uses both.
- `retry_workflow`, `restart_service` and `open_ticket` call webhooks on a small mock service in the demo.

### 11.3 Runbook runs

When an alert fires, a **runbook run** is created: a state machine stored in Postgres, one row per step.

```
step:  pending → (awaiting_approval | awaiting_answer | awaiting_manual →) running → succeeded | failed | skipped
```

`awaiting_answer` is an unparsed guard waiting for a yes / no, `awaiting_manual` a `manual` step waiting to be ticked
off. Gates are checked guard → approval → manual. A structured guard that is still false keeps the step `pending` and
the run waits there. A failed step does not stop the run, because later steps may be guarded on its failures.
Decisions and permissions: [DOMAIN.md §6](DOMAIN.md#6-lifecycles).

- Steps are executed by the **executor**, part of the `worker` role. It picks up runnable steps from a
  Postgres job table with `SELECT … FOR UPDATE SKIP LOCKED`. Actions are low-volume, so they use no topic.
- Approvals are given in the UI. **(optional)** Approving by SMS reply (`YES 4821`): the fake SMS gateway
  posts the reply to the API.
- Every step transition, approval and manual tick is written to the audit log with who did it (`RUN-5`).
- The UI shows the run on the alert. Email shows the full steps; SMS shows a short link (`RUN-2`).

### 11.4 Guards and escalation

The brief's settlement runbook:

```yaml
runbook: settlement-timeout
matches:
  type: WORKFLOW_FAILED
  "error.code": TIMEOUT
steps:
  - check: "Is counterparty-service healthy?"
    action: http_get
    url: "http://counterparty-service/health"
  - action: retry_workflow
    workflowId: "{{workflowId}}"
    approval: none
  - if: "retry fails twice"
    action: escalate
    team: counterparty-support
    approval: required
```

How it runs:

1. `http_get` runs automatically. Its result is shown on the alert.
2. `retry_workflow` runs automatically (attempt 1).
3. The retried workflow fails again, so a new `WORKFLOW_FAILED` event arrives with the same `workflowId`.
   Dedup attaches it to the **same alert**, because `workflowId` is in the fingerprint. An occurrence of the
   alert after a retry step ran counts as **a failed retry**. The retry step runs again (attempt 2).
4. After the second failure, the guard `retry fails twice` is true. The `escalate` step becomes
   `awaiting_approval` and the UI shows an "Approve escalation" button.
5. On approval, the target team is added to the alert's recipients and deliveries are produced using its
   preferences, e.g. `critical → phone + SMS`. The alert is marked `escalated`.

The retry webhook only confirms the retry was accepted, not that it succeeded. Counting repeat occurrences
on the same alert detects failure without a callback from the workflow engine.

**Guards** (`if`):

- Known phrases are parsed into a structured `StepGuard`, e.g. `<step> fails (once|twice|N times)` →
  `{"step": "retry_workflow", "failures_gte": 2}`.
- **Anything not recognised becomes a human decision point:** the UI asks "retry fails twice?" with Yes / No
  buttons. An unknown guard never breaks the runbook.

## 12. Backend and frontend

### 12.1 API

Entities, permissions, lifecycles and the endpoint list: **[DOMAIN.md](DOMAIN.md)**.

- FastAPI, structured like the existing scaffold: one package per entity with `router` → `service` →
  `models`. Routers never import models.
- Entities: teams, users, channel preferences, sources, schemas, rules, runbooks, alerts, deliveries, audit
  log.
- **Live feed (`UI-1`):** Server-Sent Events, already used by the scaffold (`EventSourceResponse`). Each API
  replica listens to Postgres `NOTIFY alert_changed` and pushes the change to its connected browsers. SSE is
  enough because the feed is one-way; acknowledge and resolve are ordinary REST calls.
- Every state change by a user (acknowledge, resolve, approve an action, edit a rule) is written to an
  append-only `audit_log` table in the same transaction (`RUN-5`).

### 12.2 Persistence

- PostgreSQL 18 with SQLAlchemy (async). Schema changes go through Alembic migrations, applied by the one-shot
  `migrate` compose service before anything else starts.
- `jsonb` columns for rule conditions, event schemas and alert payload snapshots.
- Migrations MUST be backward-compatible (expand first, contract later), so roles can be updated one at a
  time.

### 12.3 Frontend

- React 19, TanStack Router and Query, Tailwind. The API client is generated by `orval` from
  `contract/openapi.json`.
- Served by Caddy, which also proxies `/api/*` to the API, so the browser has a single origin.
- Main views: live alert feed, alert detail (runbook, actions, history), rule builder, channel preferences,
  simulated phone panel.

## 13. Observability

The scaffold already exports OpenTelemetry to `grafana/otel-lgtm` (`--profile observability`).

| Signal  | What                                                                                                     |
|---------|----------------------------------------------------------------------------------------------------------|
| Metrics | `events_ingested_total{source}`, `events_rejected_total{reason}`, `rule_eval_duration_seconds`, `alerts_created_total`, `deliveries_total{channel,status}`, `delivery_retries_total`, consumer lag per partition |
| Latency | `end_to_end_latency_seconds` histogram: `now - received_at_ms`, recorded when a delivery is sent. Grafana shows **p50 / p99** (`NFR-3`). |
| Traces  | One trace per event across all roles, propagated through Kafka headers.                                 |
| Logs    | Structured JSON (structlog) with `event_id`, `alert_id`, `rule_id`, `trace_id`.                          |
| Health  | `/health` on every role, used by compose healthchecks.                                                   |

A Grafana dashboard is committed to the repo. It is used live in the video while the load test runs and
workers are scaled.

## 14. Open questions

- **`UI-4`:** what does "propose fixes / enhancements to the alerts" mean? Users suggesting changes to a rule,
  template or runbook (review-style)? System-generated suggestions (e.g. "this rule is noisy, raise the
  threshold")? To be clarified with the mentors.
- **Schema resolution:** is an event's schema fixed per source instance, or chosen by a discriminator field
  in the payload? Proposal: per source instance, with an optional discriminator field in the source config.
- **"Problem goes away" (`RUN-5`):** how is this detected — a resolving event, absence of events for a
  period, or a health check?
