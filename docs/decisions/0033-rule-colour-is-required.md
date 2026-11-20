# ADR-0033: Rule colour is required

- **ID:** ADR-0033
- **Timestamp:** 2026-11-20T23:55+01:00
- **Status:** Accepted
- **Supersedes:** the severity → colour fallback in ADR-0032
- **See:** SPEC.md §8, DESIGN.md §4.3, REQUIREMENTS.md `RUL-4`

## Decision

`Presentation.colour` is a required `Colour`; `null` is no longer accepted. Every rule states the colour of its
alerts, and an alert shows its rule's colour.

The severity → colour map from ADR-0032 (critical → red, error → orange, warn → yellow, info → blue, debug → grey)
stays in the frontend as the rule editor's default. Picking a severity pre-fills the colour until the author
changes the colour by hand.

## Rationale

- `RUL-4` makes colour part of each rule's presentation. With a required field the stored rule says exactly what
  the UI shows, and no consumer needs its own fallback.
- The editor keeps the convenience of the old fallback, so authors still get a sensible colour without choosing
  one.
- This retypes an existing field, which SPEC §4.1 does not allow. It is a one-off exception: every rule endpoint
  still answers `501`, nothing writes to the `rules` table yet (migration 0007), and no client sends rules.
  Stored `presentation` values are validated as the DTO when loaded (ADR-0030), so a row without a colour
  would fail to load; there are none.
