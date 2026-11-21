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
| ADR-0060 | [Rule evaluator semantics, fingerprint encoding and personal-rule scope](0060-rule-evaluator-semantics-fingerprint-and-personal-rule-scope.md) | 2026-11-21T12:00+01:00 |
| ADR-0061 | [Source adapters and ingest replies](0061-source-adapters-and-ingest-replies.md) | 2026-11-21T03:30+01:00 |
| ADR-0062 | [Source catalog reloaded on NOTIFY over one listening connection](0062-source-catalog-reloaded-on-notify.md) | 2026-11-21T03:35+01:00 |
| ADR-0063 | [Ingest fails closed when the listening connection is lost](0063-ingest-fails-closed-when-the-listener-is-lost.md) | 2026-11-21T03:40+01:00 |
| ADR-0064 | [Ingest paths per source type and `has_token` on sources](0064-ingest-paths-and-token-state-on-sources.md) | 2026-11-21T03:42+01:00 |
| ADR-0065 | [Ingest matches each event against the team's schemas](0065-ingest-matches-events-against-team-schemas.md) | 2026-11-21T04:20+01:00 |
| ADR-0066 | [Grafana LGTM in the default compose stack](0066-grafana-lgtm-in-the-default-compose-stack.md) | 2026-11-21T03:30+01:00 |
| ADR-0067 | [Committed Grafana dashboard on stable HTTP semantic conventions](0067-committed-grafana-dashboard-on-stable-http-semantic-conventions.md) | 2026-11-21T04:00+01:00 |
| ADR-0068 | [Soft delete runbooks](0068-soft-delete-runbooks.md) | 2026-11-21T14:00+01:00 |
| ADR-0069 | [Runbook parsing rules](0069-runbook-parsing-rules.md) | 2026-11-21T14:05+01:00 |
| ADR-0070 | [Rule builder edits a draft tree, not the AST](0070-rule-builder-edits-a-draft-tree-not-the-ast.md) | 2026-11-21T05:00+01:00 |
| ADR-0071 | [Runbook editor: debounced parse preview, approval defaults copied from SPEC](0071-runbook-editor-parse-preview-and-approval-defaults.md) | 2026-11-21T05:00+01:00 |
| ADR-0072 | [One-time secrets bypass the query cache](0072-one-time-secrets-bypass-the-query-cache.md) | 2026-11-21T04:45+01:00 |
| ADR-0073 | [Notifications drawer over GET /deliveries](0073-notifications-drawer-over-get-deliveries.md) | 2026-11-21T13:00+01:00 |
| ADR-0074 | [Dedup counters keyed by alert, one-round-trip claims, notification rounds on the alert](0074-dedup-counters-keyed-by-alert-and-notification-rounds.md) | 2026-11-21T03:50+01:00 |
| ADR-0075 | [Own template engine, direct replacement first](0075-own-template-engine-direct-replacement-first.md) | 2026-11-21T05:06+01:00 |
| ADR-0076 | [The alert row decides renotification](0076-the-alert-row-decides-renotification.md) | 2026-11-21T05:40+01:00 |
| ADR-0077 | [Resolving an alert deletes its dedup window](0077-resolving-an-alert-deletes-its-dedup-window.md) | 2026-11-21T06:00+01:00 |
| ADR-0078 | [The counter flush drains atomically and restores on failure](0078-counter-flush-drains-atomically-and-restores-on-failure.md) | 2026-11-21T06:20+01:00 |
| ADR-0079 | [Typed audit actions and entity types; every change writes an entry](0079-typed-audit-log-and-audited-changes.md) | 2026-11-21T06:35+01:00 |
| ADR-0080 | [Schema builder edits a draft tree, with dnd-kit for drag and drop](0080-schema-builder-edits-a-draft-tree-with-dnd-kit.md) | 2026-11-21T06:40+01:00 |
| ADR-0081 | [Throttled deliveries merge into a digest delivery row](0081-throttled-deliveries-merge-into-a-digest-delivery-row.md) | 2026-11-21T06:50+01:00 |
| ADR-0082 | [Retry policy and permanent failures](0082-retry-policy-and-permanent-failures.md) | 2026-11-21T06:52+01:00 |
| ADR-0083 | [Throttle scope and token bucket](0083-throttle-scope-and-token-bucket.md) | 2026-11-21T06:54+01:00 |
| ADR-0084 | [Dispatch worker built from a DispatchContext](0084-dispatch-worker-built-from-a-dispatch-context.md) | 2026-11-21T06:56+01:00 |
| ADR-0085 | [Email through SMTP to Mailpit; SMS and phone simulated](0085-email-through-smtp-to-mailpit-sms-and-phone-simulated.md) | 2026-11-21T06:58+01:00 |
| ADR-0086 | [Routing channels reject an empty list](0086-routing-channels-rejects-an-empty-list.md) | 2026-11-21T07:30+01:00 |
| ADR-0087 | [Demo seed and ingest load generator in a compose overlay, with netem latency](0087-demo-seed-and-ingest-load-generator.md) | 2026-11-21T12:00+01:00 |
| ADR-0088 | [Executor gates, risk defaults and decision validity taken from PR #7](0088-executor-gates-taken-from-pr-7.md) | 2026-11-21T12:00+01:00 |
| ADR-0089 | [Runbooks attach by condition; the event view gains the schema name](0089-runbooks-attach-by-condition-schema-name-root.md) | 2026-11-21T13:00+01:00 |
| ADR-0090 | [Failed retries are detected by watching occurrences](0090-failed-retries-detected-by-watching-occurrences.md) | 2026-11-21T13:00+01:00 |
| ADR-0091 | [Soft delete rules](0091-soft-delete-rules.md) | 2026-11-21T14:00+01:00 |
| ADR-0092 | [Rule write checks and personal-rule visibility](0092-rule-write-checks-and-personal-rule-visibility.md) | 2026-11-21T14:05+01:00 |
| ADR-0093 | [The rule set is loaded per replica and dropped with the source catalog](0093-rule-set-loaded-per-replica-and-dropped-with-the-catalog.md) | 2026-11-21T08:05+01:00 |
| ADR-0094 | [`access_changed` is sent only when a personal rule's source scope can change](0094-access-changed-only-when-a-personal-rule-scope-can-change.md) | 2026-11-21T08:05+01:00 |
| ADR-0095 | [Resolving an alert closes its runbook run](0095-resolving-an-alert-closes-its-runbook-run.md) | 2026-11-21T08:05+01:00 |
| ADR-0096 | [Schema validation answers every issue with `200`](0096-schema-validate-answers-every-issue-with-200.md) | 2026-11-21T08:05+01:00 |
| ADR-0097 | [`--replicas` on `mise run stack` and `mise run demo` scales the backend](0097-mise-replicas-flag-scales-the-backend.md) | 2026-11-21T09:00+01:00 |
| ADR-0098 | [Sources of a type without an adapter stay readable](0098-sources-of-a-type-without-an-adapter-stay-readable.md) | 2026-11-21T09:30+01:00 |
| ADR-0099 | [The alert detail opens its own stream and reloads the run on `alert.updated`](0099-alert-detail-stream-reloads-the-run-on-alert-updated.md) | 2026-11-21T09:07+01:00 |
| ADR-0100 | [Ingest caches compiled event schema validators by schema version ID](0100-cache-compiled-event-schema-validators.md) | 2026-11-21T12:00+01:00 |
| ADR-0103 | [Fixed DB pool without pre-ping](0103-fixed-db-pool-without-pre-ping.md) | 2026-11-21T10:20+01:00 |
