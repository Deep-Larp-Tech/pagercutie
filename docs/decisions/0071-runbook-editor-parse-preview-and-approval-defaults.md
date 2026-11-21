# ADR-0071: Runbook editor: debounced parse preview, approval defaults copied from SPEC

- **ID:** ADR-0071
- **Timestamp:** 2026-11-21T05:00+01:00
- **Status:** Accepted
- **See:** docs/plans/frontend.md chunk 9, SPEC §11.1–§11.2, ADR-0018, ADR-0019, `frontend/src/lib/steps.ts` (approval defaults), `frontend/src/lib/runbooks.ts`,
  `frontend/src/components/runbooks/use-parse-preview.ts`

## Decision

**Parse preview.** The runbook editor parses the text with `POST /runbooks/parse` once format and text have not
changed for 400 ms. The request is a TanStack `useQuery` keyed by `{format, original}`: a newer text cancels the
older request through its `AbortSignal`, the last answer stays on screen while the next loads
(`keepPreviousData`), and switching back to an earlier text answers from the cache. While the form still holds the
saved runbook's format and text, the preview shows the saved `steps` and `attach` and sends nothing.

**Approval defaults.** The contract says a step's `approval: null` means "the action's default" but does not say
what the default is. The frontend keeps the defaults in `defaultApproval`, a `satisfies Record<Step['action'],
…>` map, and shows "Needs approval" when the step or its action's default is `required` (stricter-only,
ADR-0019):

| Action | Default | Source |
|---|---|---|
| `http_get`, `wait` | `none` | SPEC §11.2 (read-only) |
| `restart_service`, `escalate` | `required` | SPEC §11.2 |
| `retry_workflow` | `none` | The brief's YAML sets `approval: none` on it, which stricter-only allows only if the default is `none` |
| `call_webhook` | `required` | Changes another system, like a failover |
| `open_ticket`, `manual` | `none` | A ticket changes nothing running; a manual step is done by a person anyway |

**Condition.** The editor sends no `attach`; `RunbookCreate.attach` is optional and YAML's `matches:` sets it. The
preview shows the parsed condition read-only, as a sentence and as JSON.

## Options for the preview request

| | Debounced `useQuery` (chosen) | Debounced `useMutation` | Parse on Save only |
|---|---|---|---|
| Stale answers | Cancelled by key change | Must be ignored by hand | None |
| Cache for repeated text | Yes | No | No |
| Feedback while typing | After 400 ms | After 400 ms | None (`RUN-8` demo needs it) |

## Options for the approval defaults

| | Copy in the frontend (chosen) | Add `default_approval` to the contract | Badge only on explicit `required` |
|---|---|---|---|
| Correct badge for `escalate` without `approval:` | Yes | Yes | No |
| Contract change | None | Additive, backend work in another chunk | None |
| Drift risk | Table must match the backend's handlers | None | None, but hides risky steps |

## Rationale

- A debounced query gives cancellation and caching from the library instead of hand-written bookkeeping.
- Hiding the approval of a risky step the runbook did not mark would misinform a lead (`RUN-4`), so the badge needs
  the defaults; until the contract carries them, one exhaustive map keeps the copy in one place, and a new action
  fails `tsc` until it has a default. When the backend exposes the defaults, the map goes.
