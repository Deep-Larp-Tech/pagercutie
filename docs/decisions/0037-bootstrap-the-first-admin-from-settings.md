# ADR-0037: Bootstrap the first admin from settings

- **ID:** ADR-0037
- **Timestamp:** 2026-11-20T23:45+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §2, REQUIREMENTS.md `NFR-4`, ADR-0024

## Decision

`APP_BOOTSTRAP_ADMIN_EMAIL` (default unset) names the first admin. When the API starts and no user has the `admin`
role, it upserts that email as an admin: a new user gets the email's local part as `display_name` and `UTC` as
`timezone`; an existing user with that email is promoted. Once any admin exists the setting does nothing.

`compose.yaml` sets it to `admin@example.com` (overridable through the variable of the same name), and
`backend/.env.example` does the same for `mise run dev`. End-to-end tests log in as that email.

## Rationale

- Only admins create users (DOMAIN.md §3), so a fresh database has nobody to log in as. With the setting a fresh
  clone reaches a logged-in demo with `docker compose up` and no extra step (`NFR-4`).
- Compared with seed SQL in the Playwright `globalSetup`, it also fixes the demo and keeps tests independent of
  the table layout. Compared with a test-only `POST /test/reset` route, it adds no route that must never ship
  enabled and no contract change.
- The insert is `ON CONFLICT (email) DO UPDATE`, so API replicas starting at the same time write the same row
  without a race.
- The default is unset, so a deployment gets no passwordless admin it did not ask for.
