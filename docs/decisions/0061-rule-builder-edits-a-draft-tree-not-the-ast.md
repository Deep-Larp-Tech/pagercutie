# ADR-0061: Rule builder edits a draft tree, not the AST

- **ID:** ADR-0061
- **Timestamp:** 2026-11-21T05:00+01:00
- **Status:** Accepted
- **See:** docs/plans/frontend.md chunk 8, SPEC §4.3, §4.4, ADR-0015, ADR-0033, ADR-0047, `frontend/src/lib/rule-condition.ts`,
  `frontend/src/lib/rule-draft.ts`, `frontend/src/components/rules/`

## Decision

**Editor model.** The condition editor edits a draft tree (`ConditionDraft`): groups `{kind: 'group', mode: 'and' |
'or', negated, children}` and predicates `{kind: 'leaf', field, op, values, negated}`. Every node has a stable id
for React keys and error placement. Values keep the text the author typed plus its JSON type (`string`, `number`,
`boolean`, `null`), so `10,000,000` can be typed and `1` and `"1"` stay different. `not` becomes the `negated`
flag; `not(not(x))` keeps an inner negated AND group.

`fromCondition` and `toCondition` convert between the draft and the generated `Condition` with a `switch` over `op`
ending in `satisfies never`; `opArity`, `opLabel` and `opsForType` are `satisfies Record<LeafOp | FieldType, …>`
maps. A new condition variant in the backend fails `tsc` in all of them (SPEC §4.4). `toCondition` returns the AST or
a list of problems per node id, and is the only validation of the condition: the generated zod schema checks nested
conditions one level deep only (DOMAIN.md), so the builder never parses a condition with it.

The editor always shows a group at the top. A saved condition that is not an un-negated group is wrapped in an AND
group of one, and a top group of one child is sent as that child, so a bare `exists` round-trips unchanged.

**Errors.** A `422` `loc` below `condition` is walked through the draft (`locateIssue`), skipping the union tag
Pydantic puts into the path (`['and', 'args', 1, 'eq', 'value']`), and shown under that predicate's field or value.

**Form state.** The whole rule is one `RuleDraft` in `useState`, not react-hook-form; `validateDraft` checks it in
TypeScript with the limits the generated zod module exports, `toCreate` and `toUpdate` build the bodies (`PATCH`
sends only changed parts; `null` only for `description` and `runbook_id`).

**Smaller calls.**

- Routes: `/teams/$team/rules/new`, `/teams/$team/rules/$ruleId`, `/me/rules/new`, `/me/rules/$ruleId` (ADR-0047).
  A rule whose owner does not match the URL shows the 404 page, so `/me/rules/$id` never opens someone else's
  personal rule, admins included (DOMAIN.md §4).
- A personal rule's recipients are fixed to its owner (ADR-0026); only the channel override is editable, and it
  has no runbook picker (runbooks belong to teams).
- A new team rule starts with the team's on-call person as recipient, critical severity, red, five-minute dedup
  window. A loaded rule's colour counts as picked by hand, so changing its severity keeps the colour (ADR-0033).
- `POST /rules/test` cannot render the alert (`RuleTestRequest` has no presentation), so the preview renders
  `{{field.path}}` placeholders in the browser from the sample event and shows the server's `title` only when it
  sends one.

## Options for the editor model

| | Edit the generated `Condition` directly | Draft tree with conversion (chosen) | react-hook-form with a recursive field array |
|---|---|---|---|
| Type safety | Exact AST types, but every edit must produce a valid node, so half-typed values need `unknown` or casts | Draft types are ours; conversion is exhaustive on `op` | Paths into recursive arrays are untyped strings |
| Half-finished input (empty field, `10,000,`) | Not representable | Kept as typed text until save | Representable |
| Error placement | By index path, shifts when nodes move | By node id | By field path |
| `not` | A wrapper node the UI must show | A flag on the node | A wrapper node |
| Effort | Least code, most edge cases | Conversion plus tests | Most code |

## Rationale

- People type values the way they read them, and a predicate is unfinished while they type it; the draft keeps
  that state without loosening the AST types.
- Converting in one place with an exhaustive `switch` keeps the SPEC §4.4 merge check for the frontend.
- Ids keep a `422` error on the right predicate even after the author adds or removes rows.
