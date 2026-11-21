# ADR-0042: Strict TypeScript in the frontend

- **ID:** ADR-0042
- **Timestamp:** 2026-11-21T01:10+01:00
- **Status:** Accepted
- **See:** AGENTS.md "Type safety first", DESIGN.md §11, `frontend/tsconfig.app.json`, `frontend/tsconfig.node.json`

## Decision

Both frontend TypeScript projects compile with `strict: true` plus `noUnusedLocals`, `noUnusedParameters`,
`erasableSyntaxOnly` and `noFallthroughCasesInSwitch`: `tsconfig.app.json` (everything in `src/`, tests included)
and `tsconfig.node.json` (`vite.config.ts`, `vitest.config.ts`). `pnpm build` runs `tsc -b` before `vite build`,
so a type error fails the build.

Code never silences the checker: no `any`, `as unknown as`, `@ts-expect-error` or `@ts-ignore`. Maps keyed by a
generated enum use `satisfies Record<Enum, …>` so a new backend value fails `tsc` until every map has an entry.
Responses are narrowed on the generated `status` union, exhaustively (`satisfies never` in the default branch).
Type-level tests use vitest's `expectTypeOf`.

Generated files are exempt from the rules they cannot follow: `src/api/generated/` (orval) and
`src/routeTree.gen.ts` (TanStack Router, which emits `@ts-nocheck` and `as any`). Both are excluded from oxlint
and never edited by hand.

## Rationale

- The contract is generated from the backend DTOs (ADR-0028). Strict mode is what turns a contract change into a
  compile error at every consumer, instead of a runtime surprise.
- Unchecked JSON is the main source of frontend bugs in a CRUD app; strict null checks and the status unions keep
  "this might be an error body" visible at each call site.
- The alternative, strict mode later, means fixing every file at once; turning it on before the first screen costs
  nothing.
