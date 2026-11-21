# ADR-0078: Email through SMTP to Mailpit; SMS and phone simulated

- **ID:** ADR-0078
- **Timestamp:** 2026-11-21T06:58+01:00
- **Status:** Accepted
- **See:** ADR-0013, `DEL-4`, SPEC §10, `backend/src/pagercutie/pipeline/dispatch/channels/`, `compose.yaml`

## Decision

The email adapter sends over SMTP with `aiosmtplib` to `smtp_host:smtp_port` (settings `smtp_host`, `smtp_port`,
`smtp_from`; defaults point at Mailpit). Compose runs `axllent/mailpit` with SMTP on 1025 and the web UI and HTTP API
on 8025, and sets `APP_SMTP_HOST=mailpit` for the backend. The first line of the delivery message is the subject.

SMS and phone are simulated: the adapter requires `users.phone` (a missing number is a permanent failure,
ADR-0075) and succeeds. The delivery row is the record, shown in the notifications drawer (ADR-0073). The UI
adapter sends `pg_notify('alert_changed', alert_id)` and always succeeds.

## Rationale

- Real SMTP to a catch-all server shows an actual email in the demo and exercises the same failure handling a real
  provider would (4xx retry, 5xx permanent, connection errors).
- `aiosmtplib` is async, so a slow SMTP server does not block a thread per send. `smtplib` in a thread pool would.
- A log-only email adapter would leave the retry scenario untestable end to end.
- A real SMS or phone provider is outside the brief; ADR-0013 keeps replacing it to one adapter.
