# ADR-0080: Schema builder edits a draft tree, with dnd-kit for drag and drop

- **ID:** ADR-0080
- **Timestamp:** 2026-11-21T06:40+01:00
- **Status:** Accepted
- **See:** REQUIREMENTS `SCH-3`, ADR-0070, DESIGN.md §2 and §9, `frontend/src/lib/schema-draft.ts`,
  `frontend/src/components/event-schemas/schema-builder.tsx`

## Decision

**Editor model.** The new event schema page has two modes, **Builder** and **JSON**. The builder edits a
`SchemaDraft`: a top-level object of `PropertyDraft`s (`name`, `required`, `node`) whose nodes form a
discriminated union on `type` (`string`, `number`, `integer`, `boolean`, `null`, `object`, `array`, `literal`).
Every node and property has a stable id for React keys, drag ids and error placement. Constraint values keep the
text the author typed until `toJsonSchema` builds the document, the same way ADR-0070 keeps rule values.
`toJsonSchema` switches over `type` ending in `satisfies never` and returns the JSON Schema or problems per id
(empty or duplicate names, unreadable numbers, minimum above maximum, an invalid pattern).

**What the builder covers.** Nested objects (`properties`, `required`, `additionalProperties: false` as "Only
listed fields"); lists with one item schema (`items`, `minItems`, `maxItems`, `uniqueItems`); optional fields (not
in `required`) and nullable fields (`type: [X, "null"]`); literal types (one value as `const`, several as `enum`,
scalars only); text `minLength`, `maxLength`, `pattern`, `format`; number `minimum`, `maximum`; `description` on any
node; `$schema` on the root.

**Unsupported schemas.** `fromJsonSchema` refuses a document that uses anything else (`$ref`, `$defs`, `oneOf`,
tuples, other keywords, a `type` next to fixed values that some value does not meet, `required` names missing from
`properties`) and lists each part with its JSON pointer. Such a schema opens in JSON mode; the builder
shows the reasons and **Edit as JSON**. Reading never writes the JSON text; only an edit in the builder does, so a
new version that starts from an existing schema is sent unchanged unless the author edits it. Switching from JSON
back to Builder reads the text again only when it changed since the builder last read or wrote it, so unfinished values
and their problems survive the round trip. While the draft has
problems the JSON keeps its last valid version and saving is blocked.

**Drag and drop.** `@dnd-kit/core`: palette types are draggable, each field drags by its handle, and drop slots sit
before, between and after the fields of every object. The nearest slot to the pointer wins, ties going to the more
deeply nested slot. Slots inside the dragged field are turned off. The keyboard path is each field's actions menu:
**Move up**, **Move down**, **Move into** the object above, **Move out of** the parent, **Remove field**; palette
types add a field at the end on click.

## Options for drag and drop

| | motion `Reorder` (in the stack) | `@dnd-kit/core` (chosen) | Native HTML5 drag and drop |
|---|---|---|---|
| Palette to canvas | No | Yes | Yes |
| Move a field into or out of a nested object | No, sibling reorder only | Yes, drop slots per object | Yes |
| Touch | Yes | Yes (pointer events) | No |
| Keyboard | Own buttons | Own menu (its keyboard sensor needs sortable coordinates) | None |
| Cost | None | One runtime dependency | No dependency, more event code |

## Options for unsupported keywords

| | Refuse with reasons (chosen) | Carry unknown keywords per node |
|---|---|---|
| Type safety | Draft types are exact | Needs an `unknown` bag on every node |
| Round trip | JSON mode keeps everything | Builder keeps unknown keywords it cannot show |
| Effort | Small | Merge rules for keywords that clash with builder edits |

## Rationale

- `SCH-3` asks for sub-schemas, type constraints and type-dependent value constraints; the builder covers those
  and leaves the rest of JSON Schema to the JSON mode, which already exists.
- Moving a field between objects is the drag that nested objects need, and motion cannot do it.
- Refusing keeps the draft types exact (AGENTS.md rule 1) and never hides part of a schema behind the builder.
