# ADR-0043: A step and its action live in one class; a step may have none

- **ID:** ADR-0043
- **Timestamp:** 2026-11-21T14:00+01:00
- **Status:** Accepted
- **See:** SPEC §11.2, §11.3; amends ADR-0040, ADR-0042

## Decision

- Each step model holds its own action. `StepBase` declares an abstract `run(context: ActionContext) -> Action | None`
  (`runbooks/steps.py`): every step returns the action that performs it, or None when it has nothing to run.
  `Manual.run` returns None; a `manual` step succeeds once a human ticks it off (`awaiting_manual → succeeded`, no
  `running`, 0 attempts).
- `Action` (`runbooks/actions.py`) stays an ABC whose `async run() -> ActionResult` performs the work. `ActionFactory`
  is removed. `ActionContext` carries the integrations a step uses to build its action and is empty until the first
  concrete action.
- The factory builds gates only: `StepFactory` becomes `GateFactory` and `StepHandler` becomes `StepGates`.
  `RunbookRun` takes a `GateFactory` and an `ActionContext`, calls `step.run(context)` when the step's gates are open,
  and runs the returned action.
- Every step's `run()` except `Manual` raises `NotImplementedError` until its integration exists (HTTP client, mock
  service, escalation).

## Rationale

- One class shows a step's fields, its action and whether it has one; the optional return says in the type that
  some steps cannot be acted on.
- Building an action is separate from performing it, so a step's `run()` stays synchronous and the run records
  `running` only for steps that do work.
- Integrations come in through `ActionContext`, so steps stay plain pydantic models that the contract exports
  unchanged.

## Type guarantee

Before, `ty` failed when a step type had no action, through the exhaustive `match` in the factory. Now `run()` is
abstract on `StepBase`: a step that forgets it stays abstract, `ty` reports `abstract-class-instantiation` where it
is constructed in code, and pydantic raises `TypeError` when it is parsed (both verified). `requires_approval` still
matches every step type exhaustively.
