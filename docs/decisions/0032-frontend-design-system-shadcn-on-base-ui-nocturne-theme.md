# ADR-0032: Frontend design system: shadcn/ui on Base UI, Nocturne theme

- **ID:** ADR-0032
- **Timestamp:** 2026-11-20T23:30+01:00
- **Status:** Accepted; the severity → colour fallback is superseded by ADR-0033
- **See:** DESIGN.md, SPEC.md §12.3, REQUIREMENTS.md `UI-1`, `UI-5`, `UI-6`, `RUL-4`

## Decision

- **Components:** shadcn/ui with Base UI primitives, copied into `frontend/src/components/ui` and restyled with our
  tokens. Motion for layout and list animation (live feed enter / exit / reorder), `tw-animate-css` for simple
  keyframes, `sonner` for toasts, `cmdk` for the command palette, lucide icons, Geist and Geist Mono
  (self-hosted from npm, no Google Fonts link).
- **Brand direction "Nocturne":** violet accent (oklch hue ≈ 287) on cool graphite neutrals. Two themes, light and
  dark, as oklch tokens on `:root[data-theme]`, mapped to Tailwind v4 through `@custom-variant dark`. The user picks
  light, dark or system; the choice is applied before first paint.
- **Alert palette is separate from the brand:** one token per `Colour` value (red, orange, yellow, green, blue,
  grey) per theme, shared by every brand direction. The brand accent is never used to mean alert state.
- **Severity → colour when a rule's `colour` is null** (superseded by ADR-0033, the map is now the editor default): critical → red, error → orange, warn → yellow, info → blue,
  debug → grey. Green is only ever chosen explicitly. The map lives in the frontend, keyed by the generated
  `Severity` and `Colour` types with `satisfies Record<…>`.
- **Alert status is shown by shape, not hue:** open = solid bar and pulsing dot, acknowledged = dashed bar and ring,
  resolved = faded. Severity is always icon + label, never colour alone (`UI-6`).
- **Motion** only reports a change (new alert, repeat occurrence, status change) and uses the tokens in
  DESIGN.md §8. Under `prefers-reduced-motion` it falls back to short fades.
- **Contrast:** every text pair meets WCAG AA in both themes. The one exception is the light-theme yellow bar,
  which never carries meaning on its own (DESIGN.md §4.4).

## Rationale

- The frontend already depends on the shadcn/ui set (Tailwind v4, cva, clsx, tailwind-merge, tw-animate-css,
  lucide, motion). Base UI has been shadcn's default primitive layer since July 2026. Owning the source keeps the
  look custom. Mantine and HeroUI would bring a second styling system or a fixed look; raw React Aria would mean
  building every component.
- Violet is far from every alert hue, so the chrome never competes with the alert colours. The orchid and
  monochrome directions were rejected: orchid sits too close to red, and monochrome had too little identity.
- Using shape for status leaves hue free for the per-rule colour (`RUL-4`), and the UI stays readable for
  colour-blind users and non-engineers.
- The severity map stays in the frontend because only the UI renders colour today. If email ever needs it, the
  backend can derive it as an additive contract field.
