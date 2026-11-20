# ADR-0020: Detect failed retries through repeat occurrences; unknown guards ask a human

- **ID:** ADR-0020
- **Timestamp:** 2026-11-20T21:08+01:00
- **Status:** Accepted
- **See:** SPEC §11.4

## Decision

A repeat occurrence of the same alert after a retry step counts as a failed retry. Known guard phrases (`retry fails twice`) parse into structured guards; anything else becomes a yes/no question in the UI.

## Rationale

- The retry webhook only confirms acceptance; repeat events reveal failure without a callback from the workflow engine.
- An unparseable guard never breaks the runbook.
