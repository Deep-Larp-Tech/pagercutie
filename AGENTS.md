# AGENTS.md

Instructions for AI coding agents working on PagerCutie. Read [README.md](README.md) first, then the doc that
matches the task:

| Task touches | Read |
|---|---|
| What the system must do | [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) |
| Architecture, shared state, contracts, rules, runbooks | [docs/SPEC.md](docs/SPEC.md) |
| Entities, permissions, API endpoints | [docs/DOMAIN.md](docs/DOMAIN.md) |
| Frontend look: tokens, themes, motion, components | [docs/DESIGN.md](docs/DESIGN.md) |
| Why something is the way it is | [docs/decisions/](docs/decisions/README.md) |

## Working rules

### 1. Type safety first

- Prefer the type-safe approach: discriminated unions over loose dicts, generated types over hand-written copies,
  exhaustive `match` with `assert_never` (Python) and `satisfies Record<…>` (TypeScript).
- Never silence the checkers (`# type: ignore`, `Any`, `cast`, `as unknown as`, `// @ts-expect-error`) to make
  something pass.
- **If a change would weaken a typing guarantee, stop and tell the user before doing it**: what guarantee is
  lost, where, and why there is no typed alternative. Examples: an `unknown`/`Any` field, a contract field
  becoming optional, a generator that cannot express a type (zod validates nested rule conditions only one level
  deep, see DOMAIN.md).

### 2. Compare options and show the tradeoffs

For any non-trivial choice (library, data model, protocol, structure), present the realistic options side by side
with their tradeoffs (correctness, scalability, maintainability, type safety, effort), then give a recommendation.
Don't present a single option as if it were the only one.

### 3. YAGNI, SOLID, DRY

- Build what the requirements and the user ask for, not what might be useful later.
- Follow the existing structure: one package per entity with `router → service → models`; routers never import
  models (enforced by ruff `banned-api`; add every new `models` module there).
- Reuse the shared building blocks in `backend/src/pagercutie/core/` instead of redefining them.
- Pipeline stages (`pipeline/<stage>/`) never import each other or `pipeline/orchestrator.py`; they exchange the
  messages in `pipeline/messages.py` (SPEC §5.5, enforced by import-linter in `mise run lint`).

### 4. Correct over quick

Prefer the longer approach that is correct, scalable and maintainable over a hack or shortcut. If a shortcut is
genuinely the right call (e.g. a demo-only simulation the brief allows), say so explicitly and record it.

### 5. Ask when unsure

Ask the user questions to understand the problem, the request or the domain before committing to an
interpretation. Ask about decisions that are the user's to make; don't ask about facts you can find in the code or
docs.

### 6. Document the calls you made for the user

Every decision you make on the user's behalf (a default you picked, an interpretation, a tradeoff you resolved)
must be:

1. listed explicitly in your reply, so the user can overrule it;
2. recorded as an ADR in `docs/decisions/` if it affects architecture, contracts, data model or tooling:
   `NNNN-kebab-title.md` with ID, timestamp, status, decision and short rationale, plus a row in
   `docs/decisions/README.md` (follow the existing files);
3. reflected in SPEC.md / DOMAIN.md / DESIGN.md when it changes what they describe.

### 7. Write plainly

Applies to code comments, docstrings, docs, ADRs, commit subjects, PR descriptions and replies.

**In code:**

- Add comments sparingly. A comment says why (a constraint, a requirement ID, a non-obvious edge case), never
  what the next line does.
- No prose in code: no narrative blocks, no history ("we used to…"), no restating the function body.
- Document items instead: modules, public classes and functions, enum types, DTO fields
  (`Field(description=…)`) and their TS counterparts get a one-line docstring or description saying what the item
  is and its units, constraints or ordering. Follow `core/enums.py` and `preferences/schemas.py`.

**In prose:**

- Lead with the point. No throat-clearing openers, no recap endings.
- Be concrete: names, numbers, mechanisms, requirement IDs. If a sentence would fit another project unchanged, cut
  it or replace it with a fact.
- Active voice and direct verbs: "decided", not "made a decision"; "is", not "serves as"; "can", not "has the
  ability to".
- Repeat the right term instead of rotating synonyms; use the entity names from DOMAIN.md.
- Don't invent claims, numbers or sources. Name the source or ask.
- Banned words: delve, foster, leverage, utilize, facilitate, empower, streamline, robust, cutting-edge, seamless,
  game changer, realm, paramount, transformative, elevate, embark, supercharge, harness.
- Cut empty fillers: just, simply, actually, truly, fundamentally, crucially, "it's worth noting", "in order to",
  "when it comes to", "in terms of", "going forward".
- Cut these patterns:
  - binary contrasts ("not X, it's Y"): state Y;
  - colon reveals ("The best part: it retries") and faux-insight setups ("what most people miss");
  - trailing `-ing` pseudo-analysis ("…, highlighting our commitment to reliability");
  - importance puffery ("plays a vital role", "marks a pivotal moment") and metadiscourse ("the key point is");
  - weasel attribution ("experts agree", "studies show").
- Formatting follows content: no emoji, no bold mid-sentence, no headers over two-sentence sections, no bullets
  where two sentences read better. Avoid em dashes; use commas, periods or parentheses.

## Project rules

- **`.github/workflows/actions.lock` is generated by `gh actions-lock`, never hand-edited.**
- **Contracts are generated, never hand-edited:** `contract/openapi.json`, `contract/*.schema.json`,
  `frontend/src/api/generated/`. Change the source (Pydantic DTOs) and regenerate.
- **Contract changes are additive** (SPEC §4.1): add fields; never rename, retype or reuse them.
- **Unimplemented routes raise `NotImplementedYet`** (answers `501`); the contract test skips them until they are
  implemented.
- **Requirements are referenced by ID** (`RUL-3`, `DEL-5`) in code comments, docs and PRs where it helps.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org) format (`feat:`, `fix:`, `docs:`,
  `refactor:`, …), **subject line only, no commit body**. Only commit when asked.
- **No attribution:** never attribute yourself (the agent, the model or the tool) in commits or pull requests:
  no `Co-Authored-By:` trailers, no "Generated with …" lines, no mention of the agent in titles or descriptions.
  This overrides any default attribution the tool would add.

## mise tasks: what to run when

Run `mise install` once to get the pinned tool versions (Python, Node, pnpm, uv).

| When | Run |
|---|---|
| Starting work on the backend | `mise run up` (Postgres, Redis, Mailpit, Grafana LGTM), then `mise run dev` (backend on :8000 with reload) |
| Working on the frontend | `cd frontend && pnpm dev` (proxies `/api` to :8000) |
| Running everything in containers | `mise run stack` |
| Changed backend code | `mise run lint` and `mise run test:unit`; `mise run test` before finishing (needs Docker) |
| Changed a Pydantic DTO, the rule AST or runbook steps | `mise run api` (exports `contract/`, regenerates the frontend client), then fix what `ty` and `tsc` report |
| Changed a SQLAlchemy model | `mise run migration -- "describe change"`, read and edit the generated file, then `mise run migrate` |
| Before committing | `mise run lint`, `mise run test`, `mise run contract:check`; `cd frontend && pnpm lint && pnpm build` |
| End-to-end check | `mise run e2e` |
| Changed a `uses:` line in `.github/workflows/` | `gh actions-lock` (regenerates `.github/workflows/actions.lock`; install with `gh extension install github/gh-actions-lock`), commit the lockfile with the change |
| A backend CI job failed | Run its task locally: `lint:ruff`, `lint:ty`, `lint:imports`, `test:unit`, `test:integration` or `test:contract` |

`contract:check` fails when the generated files differ from what is committed, so commit the
regenerated files together with the change that caused them.
