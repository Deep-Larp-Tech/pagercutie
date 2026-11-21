# ADR-0060: Rule evaluator semantics, fingerprint encoding and personal-rule scope

- **ID:** ADR-0060
- **Timestamp:** 2026-11-21T12:00+01:00
- **Status:** Accepted
- **See:** SPEC §4.3, §5.3, §8.1, §9, DOMAIN.md §4, ADR-0045

## Decision

- **Evaluator location:** a pure `rules/evaluator.py` compiles a `Condition` to a closure over a mapping view of the
  event (`source`, `schema_id`, `severity`, `payload`). `pipeline/evaluation` calls it; `POST /rules/test` will
  call it too.
- **Field root:** only those four names. A segment of ASCII digits indexes into an array.
- **Equality** is JSON equality: `1 == 1.0`, bools are never numbers, numbers never equal strings. `ne` and
  `not_in` negate `eq` and `in` for a present scalar, so a type mismatch makes them `true`. Orderings on a type
  mismatch are `false`.
- **Glob:** `*` and `?` over code points, case-sensitive, no `[...]`, matched with a greedy two-pointer
  algorithm.
- **Depth:** conditions nest at most 32 levels, checked by an `AfterValidator` on the rule DTOs. The JSON Schema
  is unchanged.
- **Fingerprint:** SHA-256 of the ASCII canonical JSON `[rule_id, value, …]` (sorted keys, no whitespace,
  `\uXXXX` escapes). A missing field counts as `null`.
- **Personal-rule scope:** each compiled rule carries `AnySource` (team rules, admins' personal rules) or
  `TeamSources(team_ids)` (the owner's teams, any role). A new `access_changed` NOTIFY reloads the rule set when a
  membership or a global role changes.
- **Match order:** `evaluate` returns matches sorted by rule ID.
- **Fixtures:** `contract/rule-tests/*.json` (`{name, condition, event, expected}`) and
  `contract/fingerprint-tests.json` (`{name, rule_id, fields, event, canonical, sha256}`), hand-written.

Options considered:

| Question | Option | Tradeoff |
|---|---|---|
| Evaluator location | **Pure module in `rules/`** (chosen) | One evaluator for the API and the pipeline; import-linter stays as is. |
| | Inside the stage, copied for `/rules/test` | Two evaluators drift apart. |
| | Let `rules` import `pipeline` | Breaks the ADR-0045 boundary. |
| Personal-rule scope | **Scope in the rule set, `access_changed` reload** (chosen) | Never alerts on a source the user cannot see; one more NOTIFY. |
| | Leave it out for now | Personal rules would match every source. |
| | Check in dedup or routing | The alert would already exist before the scope check. |
| Fingerprint encoding | **Canonical JSON array** (chosen) | Typed values, unambiguous, reproducible with `serde_json`. |
| | Values joined with a separator | Ambiguous when a value contains the separator; types collapse. |
| | Python `repr` | Not portable to Rust. |
| `ne` on a type mismatch | **`true`, the negation of `eq`** (chosen) | `ne` and `not_in` read as "is not"; mixed-type `not_in` lists behave. |
| | `false`, by the "type mismatch is false" rule | `ne "ok"` against `500` would be `false`. |
| Depth limit | **Validator on the DTOs** (chosen) | One check, no contract change. |
| | Iterative evaluator | More code; still no bound on stored rule size. |

## Rationale

- The user chose these options (evaluation-stage plan, 2026-11-21).
- `json.dumps` handles integers beyond 64 bits and lone surrogates, which orjson rejects; `ensure_ascii` keeps the
  hashed bytes free of encoding errors. A Rust port needs `serde_json` with `arbitrary_precision` and its own
  `\uXXXX` escaping to reproduce the vectors.
- Missing and `null` share a fingerprint, so an event without the dedup field and one with `null` group together.
  `1` and `1.0` do not, although they are equal in conditions.
- A regex translation of glob backtracks on patterns like `*a*a*a*…b`; rule authors could slow ingest with one.
- Sorting matches gives every replica the same lock order when two of them upsert the same alerts in one
  transaction.
- `ty` reports an unhandled union variant, so SPEC §4.4 needs no second type checker.
