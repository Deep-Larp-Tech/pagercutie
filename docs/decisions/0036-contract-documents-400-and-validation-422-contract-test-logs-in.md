# ADR-0036: Contract documents 400 and the validation 422; the contract test logs in

- **ID:** ADR-0036
- **Timestamp:** 2026-11-20T23:46+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §1, ADR-0028

## Decision

- Every route with a request body declares `400` in `error_responses(...)`. FastAPI answers it when the body
  cannot be decoded, e.g. it is not UTF-8. A new body route that forgets it fails the contract test once
  implemented.
- Routes no longer declare `422` as `ErrorRead`. FastAPI documents it as `HTTPValidationError`, the list form
  that both request validation and `InvalidInput` send.
- The contract test logs in as an admin and swaps a generated `pc_session` for the real one, except on
  `/auth/logout`, which would end the shared session. Cases without a cookie still expect `401`.
- The test skips Schemathesis' `unsupported_method` check: Starlette matches by path first, so `PATCH /rules/test`
  reaches `PATCH /rules/{rule_id}` and answers `422`, not `405`.

## Rationale

- Before authentication, every route answered `501` first and the test skipped it, which hid all three gaps.
- Without a session the test would only ever see `401`, so implemented routes would never be checked.
- The `422` change retypes a documented response, but only to match what the server already sends.
