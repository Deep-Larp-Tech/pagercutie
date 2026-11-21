# ADR-0069: Runbook parsing rules

- **ID:** ADR-0069
- **Timestamp:** 2026-11-21T14:05+01:00
- **Status:** Accepted
- **See:** SPEC §11.1, §11.4, ADR-0018, ADR-0020, `backend/src/pagercutie/runbooks/parsing/`

## Decision

One pure parser per format in `runbooks/parsing/`, shared by `POST /runbooks/parse`, create and update.

- **Structured:** YAML loaded with PyYAML's `SafeLoader` (now a direct dependency; it was already installed through
  `fastapi[standard]`), validated against `StructuredRunbook`. Errors answer `422` under `loc: ["body", "original",
  …]`. YAML aliases are rejected. The `runbook:` slug must equal the runbook's `slug`. `matches:` keys are payload
  fields: `"error.code": TIMEOUT` becomes `{"op": "eq", "field": "payload.error.code", …}` inside an `and`.
- **Guards:** `<step> fails (once|twice|thrice|N times)`, optionally prefixed with `if` and with `at least`.
  `<step>` is `step N` (1-based) or a word for an action (`retry`, `restart`, `webhook`, `health check`, …), which
  resolves to the nearest earlier step with that action. `StepGuard.step` is a 0-based index, so `retry fails twice`
  in the settlement runbook is `{"step": 1, "failures_gte": 2}`. Anything else stays text for a human and adds a
  warning. A structured `StepGuard` must point at an earlier step.
- **Markdown:** numbered, bulleted and checklist items (`- [ ]`) become `manual` steps; indented continuation lines
  join their item; code fences are skipped. Links stay in the step text. A link outside the list becomes an
  `Open …` step. Without list items the text is treated as free text, with a warning.
- **Link:** a single http(s) URL becomes `Open the runbook: <url>`; anything else is treated as free text, with a
  warning.
- **Free text:** one `manual` step. Text longer than 2000 characters (the `Template` limit) is split at paragraph
  breaks, then whitespace, into several steps, with a warning.
- Blank text answers `422`. Runbook text may not contain NUL bytes (`RunbookText` now uses the shared `NO_NUL`
  pattern), since Postgres `text` cannot store them.
- On update, a new `format` or `original` re-parses the steps. `attach` is the request's when given, else the
  re-parsed `matches:` when present, else unchanged.

## Rationale

- Every runbook still displays, and only the parts that parse become executable (`RUN-8`, ADR-0018).
- Aliases let a 100 kB document expand into gigabytes during validation.
- Nearest earlier step matches how people write guards ("if the retry fails") and keeps the brief's example
  structured (ADR-0021); an unresolved guard never breaks the runbook (ADR-0020).
