# ADR-0038: The step factory matches the whole step and builds its gates and action

- **ID:** ADR-0038
- **Timestamp:** 2026-11-21T12:30+01:00
- **Status:** Accepted, amended by ADR-0039
- **See:** SPEC §11.2, §11.3, §11.4; amends ADR-0030

## Decision

- `ActionFactory` becomes `StepFactory` (`backend/src/pagercutie/runbooks/factory.py`). `create(step)` returns a
  `StepHandler` (`runbooks/gates.py`) with three gates and the action: `guard` from the `if` field, `approval` from
  the risk defaults, `confirmation` for `manual` steps, then `action` from the action type.
- A `Gate` returns the status the step must wait in, or None when open. It reads the step's `Clearance` (what humans
  have answered, approved or ticked off) and the run through the `RunState` protocol (`failures(index)`). Concrete
  gates: `OpenGate`, `FailuresGuard`, `QuestionGuard`, `ApprovalGate`, `ManualGate`.
- Guard gates are abstract factory methods (`failures_guard`, `question_guard`), dispatched by an exhaustive
  `match` on `StepGuard | str | None`, like the action methods. `approval`, `confirmation`, `create` and the
  dispatchers are `@final`; `ty` rejects overriding them, so an implementation cannot loosen RUN-4.
- `RunbookRun` no longer decides gates itself: it asks `handler.waiting_for(cleared, run)`. `requires_approval`
  moves to `factory.py`. The gate order (guard → approval → manual) and the run's behaviour are unchanged.

## Rationale

- One place matches a step, so a new guard kind or step type fails `ty check` in the factory until it is handled,
  instead of in a second `match` inside the state machine.
- Gates are small objects, so a concrete factory can swap guard semantics (e.g. a time-based guard) without
  touching `RunbookRun`.

Considered and rejected: a generic `StepVisitor[T]` (moves the `match` but leaves gate logic in the state machine);
passing a run context to every action method (does not cover guards or approval).
