# ADR-0040: Logo and icon

- **ID:** ADR-0040
- **Timestamp:** 2026-11-21T01:20+01:00
- **Status:** Accepted
- **See:** DESIGN.md §12, ADR-0032

## Decision

The mark is a pager with a face on its screen, on a tile in light-theme `--primary` (`#6d4ae4`). The logo is the
mark plus the wordmark "PagerCutie" in Geist SemiBold at -0.02em, outlined to paths and coloured `--foreground`.
The app renders them through the `Logo` and `LogoMark` components (inline SVG, wordmark in `currentColor`). For use outside the app, the mark ships as one SVG for both themes and the logo as `logo-light.svg` and `logo-dark.svg`. Colours are
hex conversions of the Nocturne tokens.

## Rationale

- Of three options (plain pager, pager with a face, pager with a heart), the face plays on the name and is easy
  to tell apart from other alerting tools. The plain pager read like a credit card at 16 px; the heart read like a
  dating or health app.
- The tile uses the light `--primary` on both themes. Dark `--primary` (`oklch(0.72 0.16 287)`) is a button tint
  and too pale for a mark, and one file is simpler than two.
- Two logo files, because an `<img>` or a README cannot follow `data-theme`, and a `prefers-color-scheme` query
  inside the SVG would disagree with a user who picked Dark on a light OS (DESIGN.md §3).
- The wordmark is one colour: DESIGN.md §4.1 keeps violet off text. No alert colour is used, so the brand never
  competes with a red alert (§1).
- Outlined text renders the same everywhere without loading Geist. Hex instead of `oklch()` because favicon
  renderers and GitHub do not support `oklch()`.
