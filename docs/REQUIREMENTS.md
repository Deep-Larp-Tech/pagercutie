# PagerCutie — Requirements

This document lists **what** PagerCutie must do. **How** we do it is described in [SPEC.md](SPEC.md).

Source: *Hackathon 2026 – Software Engineering: "Flexible Alerting & Notification Service"*.

## 1. Conventions

- **MUST / SHOULD / MAY** are used as in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).
- Every requirement has an ID (e.g. `ING-1`) so we can refer to it in issues, PRs, the spec and the
  presentation.
- **[brief]** marks requirements taken directly from the hackathon task; they are not negotiable.
  Unmarked requirements are our own and can be changed by the team.
- **(optional)** marks items the brief lists as optional. They are judged under *Innovation*.

## 2. Functional requirements

### 2.1 Ingestion

- `ING-1` **[brief]** The service MUST support **at least two different source types**, e.g. a message broker
  (Kafka, RabbitMQ), an HTTP/webhook endpoint, a tailed log file, or a polled API.
- `ING-2` **[brief]** Adding a new source MUST require as little code as possible.

### 2.2 Schemas

- `SCH-1` **[brief]** Events arrive in **different schemas**. The service MUST NOT assume a single fixed
  event format. Sample events are in the brief's Appendix A.
- `SCH-2` **[brief]** Adding a new schema MUST require as little code as possible.
- `SCH-3` Schemas MUST be definable at runtime (as data, not code) and MUST support:
  1. **Sub-schemas**: a field's type can itself be a schema.
  2. **Type constraints**: each field has a primitive or compound (array, object) data type.
  3. **Type-dependent value constraints**, e.g. *"a string is at most 3 characters long"*.

### 2.3 Rules

Teams define **rules** that decide which events reach them.

- `RUL-1` **[brief]** Rules MUST be able to **filter on any field**: metadata such as source, workflow,
  schema, severity or environment, and any value in the event body, including nested ones.
  Examples: `amount > 1000000`, `error.code in [TIMEOUT, REJECTED]`.
- `RUL-2` **[brief]** Conditions MUST be combinable with **AND / OR** logic.
- `RUL-3` **[brief]** **Per-rule routing:** each rule specifies who is notified and on which channel(s).
- `RUL-4` **[brief]** **Per-rule presentation:** each rule specifies how its alert is shown: title and body
  templates, which event fields to include, severity, and colour in the UI.
- `RUL-5` **[brief]** Rules MUST be creatable and modifiable **at runtime**, through an API, the UI, or config
  files that are reloaded live, without restarting the service.

### 2.4 Delivery

- `DEL-1` **[brief]** Supported channels: **Email, SMS, Phone call, UI**.
- `DEL-2` **[brief]** Each team or user sets **channel preferences** per severity, e.g.
  `critical → phone + SMS`, `warning → email`, `info → UI only`.
- `DEL-3` **(optional) [brief]** Preferences MAY take working hours or on-call schedules into account.
- `DEL-4` **[brief]** External channels MAY be **simulated** (a mock SMTP server, a fake SMS/phone gateway
  that logs or displays deliveries, or a sandbox provider account). **Adding a real provider MUST be a small,
  isolated change.**
- `DEL-5` **[brief]** Delivery MUST survive failure: failed deliveries are **retried**, and **no alerts are
  lost** while a channel is down.
- `DEL-6` Delivery status MUST be tracked per alert, recipient and channel.

### 2.5 Noise reduction

- `NOI-1` **[brief]** **Deduplication:** the same error 500 times in a minute is **one alert with a counter**,
  not 500 alerts.
- `NOI-2` **[brief]** **Throttling or grouping** MUST be available **per rule or per recipient**.

### 2.6 Runbooks and remediation

An alert should tell people **what to do next**, not only what went wrong. **[brief]**

- `RUN-1` **[brief]** Teams attach runbooks to **rules, schemas or alert types**. Supported formats: a
  Markdown page, a link to a wiki/Confluence page, a checklist, or free text (example in the brief's
  Appendix B).
- `RUN-2` **[brief]** When an alert fires, it shows the matching runbook and next steps, **filled in with
  values from the event** (e.g. workflow ID, service name), on every channel where they fit: the full steps
  in the UI and email, a short link in SMS.
- `RUN-3` **[brief]** Steps can be **actions** as well as text: retry a workflow, restart a service, call a
  webhook, open a ticket, escalate to another team.
- `RUN-4` **[brief]** **Risky actions require human approval** before they run, given from the UI or by
  replying to the alert.
- `RUN-5` **[brief]** The service records **what was done and by whom**, and **closes the alert when the
  problem goes away**.
- `RUN-6` **[brief]** Adding a new runbook or a new kind of action MUST be as easy as adding a rule.
- `RUN-7` **(optional) [brief]** Automatically record the steps taken to resolve incidents, so that the
  runbooks / knowledge base update themselves.

### 2.7 User interface

- `UI-1` **[brief]** **Live feed** of a team's alerts, updated in real time by push, not page refresh.
- `UI-2` **[brief]** **Acknowledge** or **resolve** an alert.
- `UI-3` **[brief]** **Manage rules and channel preferences.**
- `UI-4` **[brief]** **Propose fixes / enhancements to the alerts.** (Unclear; see SPEC open questions.)
- `UI-5` **[brief]** Each rule controls how its alerts look (see `RUL-4`).
- `UI-6` **[brief]** The UI MUST be usable by someone who has never seen it, including non-engineers.
  The rule editor MUST be understandable, and alerts MUST be clear and actionable.

## 3. Non-functional requirements

- `NFR-1` **Flexibility [brief]**: adding a new source, schema, channel or rule type should be configuration
  rather than code wherever possible. Rules should be expressive.
- `NFR-2` **Scalability [brief]**: the service MUST scale horizontally. State (rules, dedup windows,
  delivery status) MUST NOT create an obvious bottleneck or single point of failure.
- `NFR-3` **Throughput / latency [brief]**: we MUST **measure, not estimate**:
  - messages per second ingested and processed;
  - end-to-end latency from ingestion to delivery, as **p50 and p99**.

  The load-test script MUST be committed to the repo and its results included in the presentation.
- `NFR-4` **Onboarding [brief]**: going from a fresh clone to a working demo MUST take as few commands and as
  little time as possible. We track: number of commands, time to a running demo, and time for a new team to
  start receiving alerts.

## 4. Deliverables and submission

- `SUB-1` **[brief]** A Git repository with a **clear README**, including a description of **what is mocked**.
- `SUB-2` **[brief]** A **video of at most 5 minutes** explaining and showcasing the solution. It is the
  **primary basis for judging in all categories**.
- `SUB-3` **[brief]** If AI tools (Copilot, Claude, …) were used, describe **how they were used** and **how
  security and privacy concerns were addressed**.
- `SUB-4` **[brief]** Upload the video to **Lockbox**, in a directory named after the team, together with
  other resources such as a text file linking to the Git repository or a demo application.
- After the first round, judges select the top five teams to present live in the finals, followed by a Q&A.

## 5. Judging criteria [brief]

| Criterion               | Covered by                                     |
|-------------------------|------------------------------------------------|
| Flexibility             | `NFR-1`, `ING-2`, `SCH-2`, `DEL-4`, `RUN-6`    |
| Scalability             | `NFR-2`                                        |
| UX                      | `UI-6`, `NFR-4`, `SUB-1`                       |
| Throughput / latency    | `NFR-3`                                        |
| Level of implementation | `SUB-1` (README + description of what is mocked) |
| Innovation              | Items marked **(optional)**, anything extra    |
| Presentation            | `SUB-2`                                        |
