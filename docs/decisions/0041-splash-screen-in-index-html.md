# ADR-0041: Splash screen in index.html

- **ID:** ADR-0041
- **Timestamp:** 2026-11-21T02:10+01:00
- **Status:** Accepted
- **See:** DESIGN.md §8, §12.1, ADR-0040

## Decision

The splash is static markup inside `#root` in `frontend/index.html`: a copy of the `Logo` SVG plus inline CSS
that plays the "Power on" animation. React's first render replaces it. It appears only after 300 ms, repeats a
glance of the face until the app mounts, and shows a "Still loading" line after 10 s. There is no exit fade.

## Rationale

- The splash has to paint before the JavaScript bundle arrives, so it cannot be a React component.
- Inside `#root`, `root.render` removes it on first commit (checked with React 19 in jsdom), so there is no removal
  code and no way to leave it on screen by mistake. An exit fade would need that code and would delay the app by
  200 ms for decoration.
- Three copies of the logo paths (component, SVG files, `index.html`) are the cost. Rejected alternative: a Vite
  `transformIndexHtml` plugin that renders `Logo` into `index.html` at build time. It removes the copy but makes
  the build config import a `.tsx` file and depend on React server rendering, and `tsconfig.node.json` would
  need DOM types and JSX. If the copies drift, the better fix is a checked-in generator with a `brand:check` task,
  like `contract:check`.
- The 300 ms gate keeps fast loads free of a flash. The glance breaks DESIGN.md §8's "only the ping repeats"; it is
  allowed because it runs only before the first render, when no alert can be on screen.
