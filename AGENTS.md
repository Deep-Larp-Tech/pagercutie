# AGENTS.md

Instructions for AI coding agents working on PagerCutie. Read [README.md](README.md) first, then the doc that
matches the task:

| Task touches | Read |
|---|---|
| What the system must do | [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) |
| Architecture, broker, contracts, rules, runbooks | [docs/SPEC.md](docs/SPEC.md) |
| Entities, permissions, API endpoints | [docs/DOMAIN.md](docs/DOMAIN.md) |
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
3. reflected in SPEC.md / DOMAIN.md when it changes what they describe.

## Project rules

- **Contracts are generated, never hand-edited:** `contract/openapi.json`, `contract/*.schema.json`,
  `frontend/src/api/generated/`, `backend/src/pagercutie/v1/*_pb2.py*`. Change the source (Pydantic DTOs, `.proto`)
  and regenerate.
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

Run `mise install` once to get the pinned tool versions (Python, Node, pnpm, uv, buf).

| When | Run |
|---|---|
| Starting work on the backend | `mise run up` (Postgres + Redpanda), then `mise run dev` (backend on :8000 with reload) |
| Working on the frontend | `cd frontend && pnpm dev` (proxies `/api` to :8000) |
| Running everything in containers | `mise run stack` |
| Changed backend code | `mise run lint` and `mise run test:unit`; `mise run test` before finishing (needs Docker) |
| Changed a Pydantic DTO, the rule AST or runbook steps | `mise run api` (exports `contract/`, regenerates the frontend client), then fix what `ty` and `tsc` report |
| Changed a SQLAlchemy model | `mise run migration -- "describe change"`, read and edit the generated file, then `mise run migrate` |
| Changed `contract/proto/**/*.proto` | `mise run proto:lint`, `mise run proto:gen`, `mise run proto:breaking` |
| Before committing | `mise run lint`, `mise run test`, `mise run contract:check`, `mise run proto:check`; `cd frontend && pnpm lint && pnpm build` |
| End-to-end check | `mise run e2e` |

`contract:check` and `proto:check` fail when the generated files differ from what is committed, so commit the
regenerated files together with the change that caused them.
