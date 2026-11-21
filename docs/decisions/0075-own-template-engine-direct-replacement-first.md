# ADR-0075: Own template engine, direct replacement first

- **ID:** ADR-0075
- **Timestamp:** 2026-11-21T05:06+01:00
- **Status:** Accepted
- **See:** SPEC §11.2, §4.1, ADR-0060

## Decision

- Templates (rule title and body, runbook step fields) use our own engine in `core/templates.py`, not Jinja2.
- `parse` compiles a template once into frozen nodes, `Text | Placeholder`; `render` walks them with a resolver
  for field paths. Filters will be a field on `Placeholder` and functions a new node, matched with `assert_never`.
- Syntax is `{{ path }}` only. Everything else between `{{` and `}}` is a syntax error, so adding filters
  (`{{ path | filter(arg) }}`) cannot change what a valid template renders today.
- The `Template` DTO type parses on validation, so the API answers `422` for a syntax error.
- Paths resolve through the evaluator's `lookup` (`rules.evaluator.template_resolver`). A path whose first segment
  is not an event root is read under `payload`; the roots win over payload keys of the same name.
- Null and missing render as an empty string; other non-string values as compact JSON with sorted keys.
- The `Missing` marker and the field path pattern moved to `core/fields.py`, shared by `FieldPath`, the evaluator
  and the engine.
- `contract/template-tests.json` holds render and reject cases for the Python and Rust implementations.

Options considered:

| Option | Tradeoff |
|---|---|
| Jinja2 `SandboxedEnvironment` | Filters and conditionals for free, minijinja for the Rust port; the whole language becomes contract and needs sandboxing because every member writes templates. |
| **Own engine, direct replacement** (chosen) | About 100 lines, exactly the syntax we document, trivial to port; filters are ours to add. |
| Mustache (`chevron`) | Logic-less with dotted paths; the library is barely maintained. |

## Rationale

- The user chose a simpler engine than Jinja2 that supports direct replacement now and functions and filters later.
- The user chose: missing and null render empty, the `{{workflowId}}` shorthand reads the payload with roots
  winning, and templates are validated when saved.
- A regex split is enough for direct replacement. When filters take string arguments, a tokenizer replaces it
  behind `parse` without changing the nodes or `render`.
