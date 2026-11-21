# ADR-0086: Routing channels reject an empty list

- **ID:** ADR-0086
- **Timestamp:** 2026-11-21T07:30+01:00
- **Status:** Accepted
- **See:** DOMAIN.md §5, SPEC §4.1, `backend/src/pagercutie/rules/schemas.py`, `frontend/src/lib/rule-draft.ts`

## Decision

`Routing.channels` is either `null` (use the recipients' preferences) or a list of at least one channel. An empty
list answers `422`. This narrows the rule contract (`minItems: 1`), an exception to the additive rule in SPEC §4.1.

## Rationale

- An empty override meant "UI only" by accident: routing always adds the UI channel, so `[]` silently dropped every
  external channel for every recipient.
- The rule builder already refuses to save an empty selection ("Pick at least one channel."), so no client sends it.
- No rule can hold `[]` yet: the rules routes still answer `501`, so the narrowing breaks no stored data.
