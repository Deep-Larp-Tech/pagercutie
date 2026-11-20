# ADR-0035: Session lifetime and cookie attributes

- **ID:** ADR-0035
- **Timestamp:** 2026-11-20T23:45+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §2, ADR-0024

## Decision

`POST /auth/login` creates a `user_sessions` row with a 12-hour lifetime (`APP_SESSION_TTL`) and sets
`pc_session` as `HttpOnly`, `SameSite=Lax`, `Path=/`, with `Max-Age` equal to the lifetime. `Secure` is off unless
`APP_SESSION_COOKIE_SECURE=true`. A user may hold several sessions; expired rows stay until logout or user
deletion. Team-role permission checks (DOMAIN.md §4) are added with the services that need them.

## Rationale

- 12 hours covers a demo day or an on-call shift without logging in again.
- `HttpOnly` keeps the token away from scripts. `Lax` blocks cross-site `POST`s (CSRF) and still sends the cookie
  to `EventSource` on the same origin.
- Caddy serves plain HTTP locally (`Caddyfile`), where a `Secure` cookie would never be sent.
- Expired rows are filtered on lookup. A cleanup job is not worth building for a demo.
