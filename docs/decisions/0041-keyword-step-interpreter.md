# ADR-0041: Keyword rules turn runbook text into steps and guards

- **ID:** ADR-0041
- **Timestamp:** 2026-11-21T12:00+01:00
- **Status:** Accepted
- **See:** SPEC §11.1, §11.4; ADR-0018, ADR-0020, ADR-0040

## Decision

- An abstract `StepInterpreter` (`backend/src/pagercutie/runbooks/interpreter.py`) applies ordered word rules to
  runbook text. Each rule is a `PhraseRule[T]`: a regular expression matched against the whole text (case and
  extra whitespace ignored, trailing punctuation dropped) and a `build()` that returns the value or None to let the
  next rule try. The first match wins.
- Step rules (`PhraseRule[Step]`) turn a Markdown checklist item into an executable step; an item no rule matches
  becomes a `manual` step, as before. Guard rules (`PhraseRule[StepGuard]`) turn `if:` text into a `StepGuard`;
  text no rule matches stays a yes / no question (ADR-0020). `resolve_guards()` applies guard rules to the text
  guards of an already parsed runbook, including structured YAML.
- Concrete interpreters choose the rules. The one concrete rule is the phrase SPEC §11.4 names,
  `FailuresGuardRule`: `[if] <step> fails once | twice | thrice | N times`. `<step>` is an earlier step's action,
  in full or by its first word (`retry`), and the latest such step is meant.
- Interpreted steps keep their action's default approval (`requires_approval`, RUN-4), so a matched
  `restart_service` or `escalate` still waits for approval.

## Rationale

- Rules are typed by what they produce, so a step rule cannot return a guard and `ty` checks every `build()`.
- Falling back to `manual` and to a question keeps the rule of §11: every runbook displays, and only the parts
  that are understood become executable.
- Regular expressions over the whole text are predictable and testable; an LLM proposal (optional in §11.1) can
  sit beside the rules later.

Considered and rejected: a single keyword → action table (cannot extract arguments such as the service name, and
cannot reject a match when the named step does not exist); matching anywhere in the text instead of the whole text
(a sentence that only mentions "restart" would run an action).

## Known limits

- No concrete step rules exist yet; which phrases map to which actions is still to be decided.
- No parser calls the interpreter yet: the Markdown parser and runbook creation must call `interpret_steps()` and
  `resolve_guards()`.
