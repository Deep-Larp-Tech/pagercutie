# Architecture decision records

One file per decision. Timestamps are reconstructed from the design session of 2026-11-20 and are
approximate to a few minutes.

| ID | Decision | Timestamp |
|---|---|---|
| ADR-0001 | [Separate requirements from specification](0001-separate-requirements-from-specification.md) | 2026-11-20T20:10+01:00 |
| ADR-0002 | [PostgreSQL with jsonb, not MongoDB](0002-postgresql-with-jsonb-not-mongodb.md) | 2026-11-20T20:20+01:00 |
| ADR-0003 | [Modular monolith with process roles](0003-modular-monolith-with-process-roles.md) | 2026-11-20T20:25+01:00 |
| ADR-0004 | [Redpanda (Kafka API) as the message broker](0004-redpanda-kafka-api-as-the-message-broker.md) | 2026-11-20T20:30+01:00 |
| ADR-0005 | [No gRPC between internal services](0005-no-grpc-between-internal-services.md) | 2026-11-20T20:35+01:00 |
| ADR-0006 | [Python first, Rust gradually](0006-python-first-rust-gradually.md) | 2026-11-20T20:38+01:00 |
| ADR-0007 | [Partition each stateful step by its own key](0007-partition-each-stateful-step-by-its-own-key.md) | 2026-11-20T20:40+01:00 |
| ADR-0008 | [At-least-once delivery with idempotent consumers](0008-at-least-once-delivery-with-idempotent-consumers.md) | 2026-11-20T20:42+01:00 |
| ADR-0009 | [Protobuf envelope managed with buf](0009-protobuf-envelope-managed-with-buf.md) | 2026-11-20T20:45+01:00 |
| ADR-0010 | [Raw events stay in the broker; invalid events go to a dead-letter topic](0010-raw-events-stay-in-the-broker-invalid-events-go-to-a-dead-le.md) | 2026-11-20T20:48+01:00 |
| ADR-0011 | [JSON Schema 2020-12 for event schemas, validated with jsonschema-rs](0011-json-schema-2020-12-for-event-schemas-validated-with-jsonsch.md) | 2026-11-20T20:50+01:00 |
| ADR-0012 | [Live UI feed over SSE, fed by Postgres NOTIFY](0012-live-ui-feed-over-sse-fed-by-postgres-notify.md) | 2026-11-20T20:52+01:00 |
| ADR-0013 | [Simulated channels behind a channel adapter interface](0013-simulated-channels-behind-a-channel-adapter-interface.md) | 2026-11-20T20:54+01:00 |
| ADR-0014 | [OpenTelemetry with Grafana LGTM; measured end-to-end latency](0014-opentelemetry-with-grafana-lgtm-measured-end-to-end-latency.md) | 2026-11-20T20:56+01:00 |
| ADR-0015 | [Rule AST as a Pydantic discriminated union on `op`](0015-rule-ast-as-a-pydantic-discriminated-union-on-op.md) | 2026-11-20T20:58+01:00 |
| ADR-0016 | [Total evaluator with ordered severity](0016-total-evaluator-with-ordered-severity.md) | 2026-11-20T21:00+01:00 |
| ADR-0017 | [Fingerprint dedup also implements grouping](0017-fingerprint-dedup-also-implements-grouping.md) | 2026-11-20T21:02+01:00 |
| ADR-0018 | [One runbook model for every input format](0018-one-runbook-model-for-every-input-format.md) | 2026-11-20T21:04+01:00 |
| ADR-0019 | [Runbook steps as a union on `action` with stricter-only approvals](0019-runbook-steps-as-a-union-on-action-with-stricter-only-approv.md) | 2026-11-20T21:06+01:00 |
| ADR-0020 | [Detect failed retries through repeat occurrences; unknown guards ask a human](0020-detect-failed-retries-through-repeat-occurrences-unknown-gua.md) | 2026-11-20T21:08+01:00 |
| ADR-0021 | [Brief examples are acceptance scenarios](0021-brief-examples-are-acceptance-scenarios.md) | 2026-11-20T21:10+01:00 |
| ADR-0022 | [Rename the project to pagercutie](0022-rename-the-project-to-pagercutie.md) | 2026-11-20T21:12+01:00 |
| ADR-0023 | [UUIDv7 identifiers plus slugs](0023-uuidv7-identifiers-plus-slugs.md) | 2026-11-20T21:22+01:00 |
| ADR-0024 | [Passwordless demo login with a session cookie](0024-passwordless-demo-login-with-a-session-cookie.md) | 2026-11-20T21:23+01:00 |
| ADR-0025 | [Global and team roles; leads approve risky steps](0025-global-and-team-roles-leads-approve-risky-steps.md) | 2026-11-20T21:24+01:00 |
| ADR-0026 | [Rules owned by a team or a single user](0026-rules-owned-by-a-team-or-a-single-user.md) | 2026-11-20T21:25+01:00 |
| ADR-0027 | [Ordered channel preference rules, weekly on-call rotation](0027-ordered-channel-preference-rules-weekly-on-call-rotation.md) | 2026-11-20T21:26+01:00 |
| ADR-0028 | [Contract-first management API with 501 stubs and a committed generated client](0028-contract-first-management-api-with-501-stubs-and-a-committed.md) | 2026-11-20T21:30+01:00 |
| ADR-0029 | [Remove the scaffold example domain](0029-remove-the-scaffold-example-domain.md) | 2026-11-20T21:45+01:00 |
| ADR-0030 | [Hand-written ORM models with DTO value objects as typed jsonb](0030-hand-written-orm-models-with-dto-value-objects-as-typed-jsonb.md) | 2026-11-20T22:10+01:00 |
| ADR-0031 | [Database conventions](0031-database-conventions.md) | 2026-11-20T22:12+01:00 |
| ADR-0032 | [Frontend design system: shadcn/ui on Base UI, Nocturne theme](0032-frontend-design-system-shadcn-on-base-ui-nocturne-theme.md) | 2026-11-20T23:30+01:00 |
| ADR-0033 | [Rule colour is required](0033-rule-colour-is-required.md) | 2026-11-20T23:55+01:00 |
| ADR-0034 | [Backend CI on GitHub Actions through mise tasks](0034-backend-ci-on-github-actions-through-mise-tasks.md) | 2026-11-20T23:59+01:00 |
| ADR-0035 | [Session lifetime and cookie attributes](0035-session-lifetime-and-cookie-attributes.md) | 2026-11-20T23:45+01:00 |
| ADR-0036 | [Contract documents 400 and the validation 422; the contract test logs in](0036-contract-documents-400-and-validation-422-contract-test-logs-in.md) | 2026-11-20T23:46+01:00 |
| ADR-0037 | [Bootstrap the first admin from settings](0037-bootstrap-the-first-admin-from-settings.md) | 2026-11-20T23:45+01:00 |
| ADR-0038 | [Redpanda only, no in-memory queue](0038-redpanda-only-no-in-memory-queue.md) | 2026-11-21T00:40+01:00 |
| ADR-0039 | [Process roles as FastAPI apps with a typed broker wrapper](0039-process-roles-as-fastapi-apps-with-a-typed-broker-wrapper.md) | 2026-11-21T00:45+01:00 |
| ADR-0040 | [Logo and icon](0040-logo-and-icon.md) | 2026-11-21T01:20+01:00 |
| ADR-0041 | [Splash screen in index.html](0041-splash-screen-in-index-html.md) | 2026-11-21T02:10+01:00 |
| ADR-0042 | [Scalable monolith instead of the broker pipeline](0042-scalable-monolith-instead-of-the-broker-pipeline.md) | 2026-11-21T02:00+01:00 |
| ADR-0043 | [Redis for shared state; Postgres decides](0043-redis-for-shared-state-postgres-decides.md) | 2026-11-21T02:05+01:00 |
| ADR-0044 | [Caddy load-balances the backend replicas](0044-caddy-load-balances-the-backend-replicas.md) | 2026-11-21T02:08+01:00 |
| ADR-0045 | [Pipeline stages as packages with typed contracts and one orchestrator](0045-pipeline-stages-as-packages-with-typed-contracts.md) | 2026-11-21T03:00+01:00 |
| ADR-0046 | [Strict TypeScript in the frontend](0046-strict-typescript-in-the-frontend.md) | 2026-11-21T01:10+01:00 |
| ADR-0047 | [Team scope in the URL](0047-team-scope-in-the-url.md) | 2026-11-21T01:11+01:00 |
| ADR-0048 | [Generated MSW mocks in dev, strict MSW in tests](0048-generated-msw-mocks-in-dev-strict-msw-in-tests.md) | 2026-11-21T01:12+01:00 |
| ADR-0049 | [Undocumented statuses get one shared fallback](0049-undocumented-statuses-get-one-shared-fallback.md) | 2026-11-21T01:30+01:00 |
| ADR-0050 | [End-to-end tests with per-test personas](0050-end-to-end-tests-with-per-test-personas.md) | 2026-11-21T02:00+01:00 |
| ADR-0051 | [Generated client through a shared fetch mutator](0051-generated-client-through-a-shared-fetch-mutator.md) | 2026-11-21T02:30+01:00 |
| ADR-0052 | [Session guard in a pathless layout, 401 through the cache hooks](0052-session-guard-in-a-pathless-layout-401-through-cache-hooks.md) | 2026-11-21T02:45+01:00 |
| ADR-0053 | [Not-found and screen errors render inside the shell](0053-not-found-and-screen-errors-render-inside-the-shell.md) | 2026-11-21T02:50+01:00 |
| ADR-0054 | [Live alert feed merges SSE events into the query cache](0054-live-alert-feed-merges-sse-events-into-the-query-cache.md) | 2026-11-21T03:30+01:00 |
| ADR-0056 | [Rotation editor: shift preview from the on-call answer, reordering with motion](0056-rotation-editor-shift-preview-and-reordering.md) | 2026-11-21T03:18+01:00 |
| ADR-0057 | [Soft delete users](0057-soft-delete-users.md) | 2026-11-20T23:33+01:00 |
| ADR-0058 | [Models as dataclasses](0058-models-as-dataclasses.md) | 2026-11-21T01:09+01:00 |
| ADR-0059 | [End-to-end tests in CI against the compose stack](0059-end-to-end-tests-in-ci-against-the-compose-stack.md) | 2026-11-21T12:00+01:00 |
| ADR-0063 | [One-time secrets bypass the query cache](0063-one-time-secrets-bypass-the-query-cache.md) | 2026-11-21T04:45+01:00 |
