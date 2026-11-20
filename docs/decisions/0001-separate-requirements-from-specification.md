# ADR-0001: Separate requirements from specification

- **ID:** ADR-0001
- **Timestamp:** 2026-11-20T20:10+01:00
- **Status:** Accepted
- **See:** REQUIREMENTS.md, SPEC.md

## Decision

`docs/REQUIREMENTS.md` lists *what* the system must do, with stable IDs (`ING-1`) and a **[brief]** tag for constraints taken from the hackathon task. `docs/SPEC.md` describes *how*.

## Rationale

- IDs let issues, PRs, the spec and the video refer to requirements precisely.
- The tag separates non-negotiable brief constraints from our own choices, which the team may change.
