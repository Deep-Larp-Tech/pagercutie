# ADR-0024: Passwordless demo login with a session cookie

- **ID:** ADR-0024
- **Timestamp:** 2026-11-20T21:23+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §2

## Decision

`POST /auth/login {email}` logs in without a password and sets the HttpOnly `pc_session` cookie.

## Rationale

- Real authentication is out of scope for the hackathon; replacing it with OIDC only touches the `auth` module.
- A cookie, not a header, because `EventSource` cannot send headers.
