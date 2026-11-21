# PagerCutie design system

The look, tokens, motion and component rules for the frontend. The design is called Nocturne: a violet accent on
cool graphite, in a light and a dark theme. The decisions behind it are in
[ADR-0032](decisions/0032-frontend-design-system-shadcn-on-base-ui-nocturne-theme.md); requirement IDs refer to
[REQUIREMENTS.md](REQUIREMENTS.md).

People open PagerCutie when something is broken, often half-awake, and some of them are not engineers (`UI-6`).
Every rule below serves that reader: the alert they need is the loudest thing on screen, its state reads without
colour, and every action says in plain words what it does.

## 1. Principles

1. **Alert colour belongs to the rule.** Each rule picks the colour of its alerts (`RUL-4`, `UI-5`). The chrome
   around them stays graphite and violet, so it never competes with a red alert.
2. **Everything reads without colour.** Severity always shows an icon and a label. Alert status is shown by shape.
   A colour-blind on-call engineer and a greyscale screenshot get the same information.
3. **Motion reports a change.** A new alert arrives, a counter goes up, someone acknowledges. Nothing moves for
   decoration, and the only animation that repeats is the live indicator on an open alert.
4. **Quiet until it matters.** Resolved alerts fade back, acknowledged ones calm down, and only open alerts keep
   their full colour.

## 2. Stack

| Concern | Choice | Notes |
|---|---|---|
| Components | [shadcn/ui](https://ui.shadcn.com) on Base UI | Source copied into `frontend/src/components/ui/` and restyled with our tokens. Never ship a component in its default shadcn look. |
| Styling | Tailwind v4 | Tokens are CSS variables in `frontend/src/index.css`, exposed to Tailwind with `@theme inline`. |
| Variants | `class-variance-authority`, `tailwind-merge`, `clsx` | One `cn()` helper in `src/lib/utils.ts` (created by `shadcn init`). |
| Layout and list motion | `motion` (`motion/react`) | Live feed enter, exit and reorder; shared-layout tabs. |
| Drag and drop | `@dnd-kit/core` | Schema builder: palette to canvas and moves between nested objects (ADR-0080). Plain list reorder stays on motion `Reorder`. |
| Simple keyframes | `tw-animate-css` | Dialog, popover and tooltip open and close. |
| Toasts | `sonner` | Transient confirmations only ("Alert acknowledged"). Errors that need action stay inline. |
| Command palette | `cmdk` | `⌘K` / `Ctrl K`: jump to an alert, rule or runbook; run Acknowledge and Resolve. |
| Icons | `lucide-react` | Already a dependency. Stroke width 1.75 everywhere, sizes 14, 16 and 20. Never draw icon paths by hand. |
| Fonts | Geist and Geist Mono | Self-hosted from npm (Fontsource `@fontsource-variable/geist` and `@fontsource-variable/geist-mono`), `font-display: swap`. No Google Fonts link. |

Before `shadcn init`, add the `@/` alias for `src/`: `"paths": { "@/*": ["./src/*"] }` in `tsconfig.json`
and `tsconfig.app.json` (no `baseUrl`, which TypeScript 7 removed), and `resolve.alias` in `vite.config.ts`. The
CLI refuses to run without it, and the examples below use it.

Shared class strings (focus ring, layer surface, open and close motion) live in
`frontend/src/components/ui/styles.ts`.

## 3. Themes

There are two themes, light and dark. The user picks **Light**, **Dark** or **System** at the bottom of the sidebar;
System follows `prefers-color-scheme` and updates when the OS switches.

- The resolved theme is set as `data-theme="light"` or `data-theme="dark"` on `<html>`, together with the
  matching `color-scheme`, so scrollbars and native controls follow.
- A small inline script in `index.html` reads the stored choice (`localStorage` key `theme`) and sets
  the attribute before first paint, so the page never flashes the wrong theme. It falls back to System when
  storage is unavailable.
- Tailwind's `dark:` variant follows the attribute, not the media query:

  ```css
  @custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));
  ```

- Switching runs inside `document.startViewTransition()` for a 250 ms cross-fade, and switches instantly when
  View Transitions are unsupported or reduced motion is on.
- The whole app has one theme at a time. No section or panel inverts.

## 4. Colour

All colours are `oklch()`, kept inside the sRGB gamut so they render the same on every screen. Neutrals carry a
slight violet tint (hue 285); there is no pure black or pure white anywhere.

### 4.1 Chrome tokens

Token names follow shadcn/ui so its components work unchanged. In shadcn, `--accent` is the subtle hover
surface; the brand violet is `--primary`.

| Token | Light | Dark | Used for |
|---|---|---|---|
| `--background` | `oklch(0.985 0.003 285)` | `oklch(0.155 0.012 285)` | Page |
| `--foreground` | `oklch(0.21 0.02 285)` | `oklch(0.965 0.005 285)` | Body text |
| `--card` | `oklch(0.997 0.002 285)` | `oklch(0.195 0.014 285)` | Alert cards, panels |
| `--popover` | `oklch(0.997 0.002 285)` | `oklch(0.215 0.015 285)` | Menus, popovers, dialogs |
| `--primary` | `oklch(0.54 0.22 287)` | `oklch(0.72 0.16 287)` | Primary buttons, focus ring, selection, active nav |
| `--primary-foreground` | `oklch(0.99 0.004 287)` | `oklch(0.17 0.03 287)` | Text on primary |
| `--secondary`, `--muted` | `oklch(0.955 0.006 285)` | `oklch(0.25 0.015 285)` | Secondary buttons, code, inactive tabs |
| `--muted-foreground` | `oklch(0.5 0.016 285)` | `oklch(0.7 0.016 285)` | Metadata, helper text, placeholders |
| `--accent` | `oklch(0.945 0.012 287)` | `oklch(0.27 0.03 287)` | Hover and highlighted rows |
| `--border` | `oklch(0.915 0.006 285)` | `oklch(0.275 0.016 285)` | Card and divider lines |
| `--input` | `oklch(0.66 0.01 285)` | `oklch(0.5 0.014 285)` | Input, select and checkbox borders |
| `--ring` | same as `--primary` | same as `--primary` | Focus outline |
| `--destructive` | alert red solid | alert red solid | Delete, disable rule |
| `--destructive-foreground` | `oklch(0.99 0.004 287)` | `oklch(0.17 0.03 25)` | Text on destructive |

`*-foreground` tokens not listed (card, popover, secondary, muted, accent) equal `--foreground`.

**Where violet goes.** Violet marks things the user can act on: primary buttons, the focus ring, selected items,
the active nav item, switches, and runbook steps waiting on a person. It never appears as an alert bar, badge or
text colour, because info alerts are blue and blue sits close to violet. Use one primary button per view.

### 4.2 Alert palette

One set of tokens per rule `Colour` value, per theme. These are the same whatever the chrome looks like.

- **solid** (`--alert-<colour>`): the left bar of an alert card, status dots, chart marks.
- **tint** (`--alert-<colour>-tint`): badge and chip backgrounds.
- **text** (`--alert-<colour>-text`): badge labels and inline values such as the error message in Team
  Settlements' alerts.

| Colour | Light solid / tint / text | Dark solid / tint / text |
|---|---|---|
| red | `0.58 0.21 25` / `0.95 0.024 25` / `0.46 0.17 25` | `0.69 0.189 25` / `0.27 0.06 25` / `0.84 0.084 25` |
| orange | `0.66 0.166 50` / `0.955 0.025 55` / `0.47 0.12 50` | `0.76 0.15 55` / `0.28 0.05 55` / `0.87 0.08 60` |
| yellow | `0.78 0.15 85` / `0.965 0.042 90` / `0.47 0.095 75` | `0.85 0.15 90` / `0.29 0.05 90` / `0.91 0.1 95` |
| green | `0.6 0.15 150` / `0.955 0.035 150` / `0.44 0.11 150` | `0.74 0.15 150` / `0.27 0.045 150` / `0.86 0.09 150` |
| blue | `0.57 0.162 252` / `0.95 0.023 252` / `0.45 0.129 252` | `0.72 0.14 252` / `0.27 0.05 252` / `0.85 0.07 252` |
| grey | `0.6 0.01 285` / `0.94 0.004 285` / `0.44 0.012 285` | `0.68 0.01 285` / `0.27 0.008 285` / `0.84 0.01 285` |

Values are `oklch(L C H)`.

### 4.3 Severity

Every rule sets `presentation.colour`; the API rejects a rule without one (ADR-0033), and an alert always shows
its rule's colour. In the rule editor, picking a severity pre-fills the colour from the table below. Once the
author picks a colour by hand, changing the severity leaves it alone. Green is never a default; it is reserved for
success and resolved states unless a rule picks it on purpose.

| Severity | Default colour | Icon (lucide) | Label |
|---|---|---|---|
| `critical` | red | `OctagonAlert` | Critical |
| `error` | orange | `CircleX` | Error |
| `warn` | yellow | `TriangleAlert` | Warning |
| `info` | blue | `Info` | Info |
| `debug` | grey | `Bug` | Debug |

The maps are keyed by the generated types, so a new severity or colour in the backend fails `tsc` until it has a
token, an icon and a label:

```ts
import { Colour, Severity } from '@/api/generated/model'

export const defaultColour = {
  critical: Colour.red,
  error: Colour.orange,
  warn: Colour.yellow,
  info: Colour.blue,
  debug: Colour.grey,
} as const satisfies Record<Severity, Colour>

export const alertColourClass = {
  red: 'alert-red',
  orange: 'alert-orange',
  yellow: 'alert-yellow',
  green: 'alert-green',
  blue: 'alert-blue',
  grey: 'alert-grey',
} as const satisfies Record<Colour, string>
```

`alert-<colour>` is a utility that sets `--c`, `--c-tint` and `--c-text` from the alert tokens, so components
read three variables and never branch on colour.

### 4.4 Contrast

Measured with WCAG 2.2 relative luminance after converting each token to sRGB.

| Pair | Light | Dark | Needed |
|---|---|---|---|
| foreground on background | 17.0 | 17.7 | 7 (AAA) |
| muted-foreground on card | 6.0 | 6.8 | 4.5 |
| primary-foreground on primary | 5.4 | 7.4 | 4.5 |
| destructive text on destructive | 4.6 | 6.4 | 4.5 |
| alert text on alert tint (lowest of six) | 6.2 | 9.1 | 4.5 |
| input border on card | 3.1 | 3.0 | 3 |
| focus ring on background | 5.3 | 7.5 | 3 |
| alert solid on card (lowest of six) | 2.0 (yellow) | 6.1 | 3 |

Light-theme yellow is the one exception. A yellow dark enough for 3:1 on white reads as orange, which would
break the difference between `warn` and `error`. The bar never carries meaning alone: the badge next to it
names the severity in text that passes at 6.3:1.

Re-run the check whenever a token changes.

## 5. Status

Hue is taken by the rule colour, so status uses shape, weight and words.

### 5.1 Alert status

| Status | Left bar | Indicator | Card | Main action |
|---|---|---|---|---|
| `open` | Solid, rule colour | Filled dot; pings when the alert is critical (§8) | Raised, full colour | **Acknowledge** (primary) |
| `acknowledged` | Dashed, rule colour | Hollow ring, avatar and "&lt;name&gt; is on it" | Raised | **Resolve** (secondary) |
| `resolved` | Faded to 35 % | Check icon, "Resolved" or "Resolved automatically" (`Resolution.auto`) | Flat, muted title | None |

The occurrence counter (`NOI-1`) sits top right in Geist Mono: `×12`.

### 5.2 Delivery status

| Status | Icon | Text |
|---|---|---|
| `pending` | `Clock` in muted | "Sending by SMS" |
| `sent` | `Check` in green | "Sent by SMS, 14:02" |
| `failed` | `CircleX` in red | "SMS failed, retrying" plus the attempt count (`DEL-5`) |

### 5.3 Runbook step status

| Status | Indicator | Colour |
|---|---|---|
| `pending` | Hollow ring | grey |
| `awaiting_approval` | Filled dot with ping, **Approve** button for leads (`RUN-4`) | primary |
| `awaiting_answer`, `awaiting_manual` | Hollow ring and the question or instruction | primary |
| `running` | Spinner | blue |
| `succeeded` | Check | green |
| `failed` | Filled dot and the error text | red |
| `skipped` | Dot, struck-through label | muted |

## 6. Typography

Geist for text, Geist Mono for anything a person might copy or compare: IDs, field paths, template placeholders
(`{{payload.workflowId}}`), counts and timestamps. Numbers use `tabular-nums` so counters do not jitter.

| Role | Size / line height | Weight |
|---|---|---|
| Page title | 24 / 32 | 600, tracking -0.02em |
| Section title | 18 / 26 | 600, tracking -0.01em |
| Alert title | 15 / 22 | 560 |
| Body, inputs | 14 / 20 | 400 |
| Metadata, badges | 12 / 16 | 500 |
| Mono values | 13 / 20 | 450 |

Hierarchy comes from weight and colour more than size. Nothing in the app is larger than 24 px.

## 7. Shape, elevation and spacing

| Element | Radius |
|---|---|
| Buttons, inputs, selects | 8 px |
| Alert cards, panels | 12 px |
| Popovers, dialogs, command palette | 14 px |
| Badges, status chips, switches | full |

Spacing follows a 4 px grid. Cards get 12 px padding in the feed and 16 px in detail views. Use cards only where
elevation means something (an alert, a dialog); group everything else with spacing and `--border` dividers.

Shadows are tinted with the neutral hue, never pure black:

| Level | Light | Dark |
|---|---|---|
| Card | `0 1px 2px oklch(0.21 0.02 285 / 6%), 0 4px 14px -4px oklch(0.21 0.02 285 / 8%)` | `0 1px 0 oklch(1 0 0 / 4%) inset, 0 8px 24px -8px oklch(0 0 0 / 50%)` |
| Popover, dialog | `0 12px 32px -8px oklch(0.21 0.02 285 / 18%)` | `0 1px 0 oklch(1 0 0 / 6%) inset, 0 16px 40px -8px oklch(0 0 0 / 60%)` |

Z-index comes from one scale in `src/lib/layers.ts`: header 10, drawer 30, popover 40, dialog 50, toast 60. Components
read it as inline `style={{ zIndex: layers.… }}` on the Base UI portal element, which is a stacking context
pinned to the viewport origin (`fixed top-0 left-0 isolate`). It must not sit in the page flow: Base UI positions
anchored popups with `position: absolute` against it, and a portal at the bottom of the page places their first
frame off-screen, which scrolls the page while focus moves into the popup.
Base UI portals a layer opened inside another layer into the parent's portal, so a select inside a dialog stacks
above the dialog without a higher number. Tooltips use the popover layer with an 8 px radius.

## 8. Motion

| Token | Value | Used for |
|---|---|---|
| `fast` | 150 ms, `cubic-bezier(0.2, 0.8, 0.2, 1)` | Hover, press, colour changes |
| `base` | 250 ms, same curve | Popovers, tabs, page change, theme cross-fade |
| `spring` | `{ type: 'spring', stiffness: 380, damping: 32 }` | Feed enter, reorder, counter bump, nav highlight |
| `exit` | 200 ms, `cubic-bezier(0.4, 0, 1, 1)` | Anything leaving |

What moves, and what it tells the user:

| Moment | Animation | Why |
|---|---|---|
| New alert in the live feed (`UI-1`) | Slides 8 px down from the top and fades in; the rest of the list shifts with `layout` | Shows where the new alert came in |
| Repeat occurrence (`NOI-1`) | Counter scales to 1.2 and back; the card tint flashes once for 900 ms | Says "this happened again" without adding a row |
| Acknowledge | Bar changes from solid to dashed, dot becomes a ring, button cross-fades to **Resolve** | Confirms the click right where it happened |
| Resolve | Card fades to the resolved style, then leaves the open feed after 700 ms | Gives the user time to see the result before it goes |
| Open critical alert | Status dot pings every 1.6 s | The only repeating animation in the app; it marks something that still needs a person |
| App still loading after 300 ms | Splash "Power on" (§12.1); the face glances every 3.2 s until the app mounts | Says the page is alive while the bundle loads; gone before any alert can show |
| Data still loading after 200 ms | Skeleton fades in (`fast`), then pulses | Says the page is waiting; a faster answer replaces it before it shows, so a fast tab switch does not flash |
| Button press | Scales to 0.97 | Physical feedback |
| Dialog, popover | Fade and scale from 0.97 (`tw-animate-css`) | Shows where the layer came from |
| Sidebar or sub-nav item picked | The active highlight slides from the old item to the new one (`spring`, motion `layoutId`) | Connects the click to the page that opens |
| Page change (path changes) | The page and the header title fade in and rise 6 px (`base`); no exit animation | Marks that the content is new; without an exit the old page never renders the new route's data |

Rules:

- Animate `transform` and `opacity` only. Height changes in the feed go through motion's `layout`, which uses
  transforms.
- Under `prefers-reduced-motion: reduce`, motion components skip movement and keep plain fades of 150 ms or less
  (`MotionConfig reducedMotion="user"` at the root; components with custom effects also read
  `useReducedMotion()`); the ping, the flash and the counter bump turn off. A global CSS rule shortens every CSS
  animation and transition to near zero.
- Motion transitions come from `src/lib/motion.ts` (`motionTokens`, `screenEnter`), never inline numbers.
- A layout with its own sub-nav sets `staticData.ownsTransitions`: the shell keys its page transition on that
  layout's path, and the layout animates its own outlet, so the sub-nav stays mounted and its highlight can slide.
- Do not stagger list items on page load. The feed renders at once; only new arrivals animate.
- The splash glance is the one exception to "only the ping repeats". It runs only before React's first render,
  so it never shares the screen with an alert.

## 9. Components

The first set, in the order the views need them. Each lists the states it must handle.

| Component | Built from | States and rules |
|---|---|---|
| `Button` | shadcn Button | `primary`, `secondary`, `ghost`, `destructive`; sizes `sm` (28 px) and `md` (32 px); labels are verbs and fit on one line |
| `SeverityBadge` | shadcn Badge | Icon and label from §4.3, tint background |
| `AlertCard` | Custom | Open, acknowledged, resolved (§5.1); title and body from the rule's templates; listed `fields` in Geist Mono; counter; recipients and channels; relative time with the absolute time in a tooltip |
| `AlertFeed` | Custom, motion | Live, reconnecting and offline states; skeleton of three cards while loading; empty state that links to the rule editor |
| `StatusIndicator` | Custom | Alert status by shape and words (§5.1) in the nearest `alert-<colour>`; the ping is the `animate-live-ping` utility (1.6 s) |
| `OccurrenceCounter` | Custom, motion | `×12` in Geist Mono, `tabular-nums`, hidden at 1; bumps on increase, not announced |
| `RelativeTime` | Base UI Tooltip | "3 minutes ago" in a focusable `<time>`, absolute date and time in the user's time zone in the tooltip |
| `FeedFilters` | shadcn ToggleGroup | Status and severity, several at once; none pressed in a group means any value |
| `ConnectionBar` | Custom | The "Live connection" states below, sticky under the header |
| `OnCallCard` | Custom | Team name, then "You're on call until Mon 09:00", "&lt;name&gt; is on call" or "No rotation set"; bordered, no shadow |
| `StepList` | Custom | Steps in order as bordered rows: action icon, label and one-line description, parameters filled from the event in Geist Mono, check question, guard, status (§5.3), attempts, failures, result, who decided. A step waiting on a person gets a violet border. **Approve step** (with a `ConfirmDialog` naming what will run) and **Reject step** only for leads (`RUN-4`); **Yes** / **No** for an unparsed guard and **Mark as done** for a manual step for members and leads; others read "Waiting for a team lead to approve." or "Waiting for a team member."; a refused decision puts the step back and shows why under it; skipped steps strike through their label |
| `Field` | Base UI Field, shadcn Input | Label above, helper text below, error text below in alert-red text; never a placeholder used as a label |
| `Combobox` | Base UI Combobox | Field paths and recipients in the rule editor, people to add to a team, time zones; keyboard first (type to filter, arrows, Enter); states: loading, no match, nothing to offer (each a muted line in the list), selected (check), invalid (red border and `FieldError`) |
| `Dialog`, `Popover`, `Tooltip` | shadcn | Focus trapped in dialogs and returned on close |
| `Toaster` | sonner | Bottom right, one at a time, 4 s; theme read from `data-theme`, no `next-themes` |
| `CommandMenu` | cmdk in `Dialog` | Opens with `⌘K` / `Ctrl K` or the header's **Search** button, which shows the platform's shortcut; returns focus on close. Groups: Alerts (open and acknowledged, from the cached feeds, five until you type), Navigate (pages the user can see), Rules and Runbooks of the current team, Actions (theme). **Acknowledge** and **Resolve** sit right under the highlighted alert, only for users who may respond, and change in place; an error shows inline in alert red. Each searched group shows one muted line while loading, on failure or with nothing to offer; a group with no match hides; "Nothing matches" when no group has a match |
| `AuditLog` | `Table` | When, Who ("You", "System" or the short id), What in plain words, Entity (type, link where a page exists, short id that filters to its history), data behind a disclosure as JSON in Geist Mono; entity type and ID filters in the address, an invalid ID shown under its field; skeleton rows, empty and filtered-empty states, failure with **Try again**, **Show more** |
| `ThemeToggle` | shadcn ToggleGroup | Sun, Moon and Monitor icon with Light, Dark, System label, full sidebar width at its bottom; stores `theme`, follows the OS while System is picked, cross-fades per §3 |
| `AppShell` | Custom | Sidebar 240 px from 1024 px, a `Sheet` below; header; content column at most 1120 px; a screen that throws shows `ScreenError` in the content area and keeps the shell (ADR-0053) |
| `Sidebar` | Custom, router `Link` | Overview; Team (switcher and team pages); Me; Admin for admins only. Items the user cannot use are hidden. Active item: `--accent` background, `--primary` text, `aria-current="page"`. No team: one muted line instead of the team pages. `ThemeToggle` pinned to the bottom |
| `TeamSwitcher` | shadcn DropdownMenu | "Your teams" with the role, then "Other teams" for admins; current team ticked in violet; keeps the current team page when switching; a documented `GET /teams` failure shows one muted line, an undocumented one (the `501` stub) shows nothing |
| `Header` | Custom | Sticky, 56 px, header layer; navigation button below 1024 px; page title from the route (`staticData.title`), prefixed with the team name inside a team; **Search** button with the `CommandMenu` shortcut; **Sent notifications** toggle for the `NotificationsDrawer`; `UserMenu` |
| `UserMenu` | shadcn DropdownMenu | Initials avatar and name; menu with name and email, **Profile**, **Sign out**; a failed sign-out keeps the menu open with the error inline |
| `PageHeader` | Custom | Page title 24 / 32 as the page's only `h1`, optional one-line description, optional actions on the right |
| `EmptyState` | Custom | 20 px icon in a muted circle, title, one line, optional action; dashed border; `role="alert"` when it reports an error (404, `ScreenError`) |
| `Sheet` | shadcn Sheet (Base UI Dialog) | Slides in from the left over a backdrop on the dialog layer; focus trapped, returned to the trigger on close; closes on navigation |
| `Skeleton` | shadcn Skeleton | Same shape as the content it stands for, no spinner; invisible for the first 200 ms so a fast answer never shows it, then fades in (`fast`) and pulses (`animate-skeleton`); keeps its space while hidden, so nothing shifts |
| `Table` | shadcn Table | Rows divided by `--border`, no card; headings in metadata type; scrolls sideways inside its box on narrow screens. Lists show skeleton rows while loading, an `EmptyState` when empty or failed (with **Try again**), and **Show more** when a page of 100 came back full |
| `ConfirmDialog` | `Dialog` | Asks before an irreversible or consequential action: the title names the thing ("Delete Anna Novak?"), one line on what follows, **Cancel** then the confirm button, destructive by default and primary for an approval (**Approve step**); buttons disable while it runs; a failure shows inline in alert red and keeps the dialog open |
| `SettingsNav` | Custom, router `Link` | Tabs under the team settings title: General, Members, Rotation, Notifications; a `--primary` underline slides to the open page (§8), which has `aria-current="page"`; the tabs stay mounted while the page below changes |
| `ChannelPreferencesEditor` | Custom | Ordered rule rows (minimum severity, channels, optional time window with days and `HH:MM` start and end, crossing midnight allowed); each row shows its rule as a sentence ("Critical and above: SMS, weekdays 08:00 to 20:00"); add, remove and move up or down; at most 20 rows (**Add rule** turns off and says why); footer "Anything else: UI only"; field errors under the field, from the client or a `422`; read-only: the sentences as a numbered list. Serves team and personal preferences |
| `RotationEditor` | Custom, motion `Reorder` | Ordered people with a drag handle and **Move up** / **Move down** buttons (the keyboard path), "On call now" badge while unchanged; handoff day, `HH:MM`, time zone `Combobox`; preview of the next four shifts, titled "after you save" once edited (ADR-0056); read-only: numbered list, handoff sentence and preview |
| `SegmentedControl` | Base UI ToggleGroup, motion | One option always selected; selected option in `--primary` text on an `--accent` highlight that slides between options (`spring`, `layoutId`); optional 14 px icon; `aria-label` names the group. Filters a view; the theme toggle keeps its own pressed style |
| `TimeZoneSelect` | Base UI Combobox | Searchable IANA zones with the current UTC offset in Geist Mono; the saved zone is always an option (`UTC` too, which browsers leave out); "No time zone matches" when the search finds nothing; the input carries the field label, the chevron is decorative |
| `DeliveryStatusLine` | Custom | Icon and words per §5.2 for every `DeliveryStatus` and `Channel`; the sent time in Geist Mono; a failed delivery shows its attempt count |
| `NotificationsDrawer` | Custom, motion | Non-modal panel 380 px wide on the right edge of every signed-in screen, opened from the header's **Sent notifications** button (pressed state while open) and remembered per browser; from 1024 px the content column makes room for it, below that it covers the page. `SegmentedControl` filter All / Email / SMS / Calls / App; deliveries newest first, new ones slide in (`spring`); skeleton, empty, error with **Try again**; Escape inside it closes it; drawer layer (§7) |
| `DeliveryItem` | Custom | One delivery: channel icon and name, recipient ("To you" or a short user id), the message as rendered for the channel, `DeliveryStatusLine`, the failure reason in alert-red Geist Mono while failing, time in Geist Mono with the full date in a tooltip |
| `AlertStatusBar` | Custom, motion | The left bar of an alert in the nearest `alert-<colour>` by status (§5.1) and the one-off tint flash on a repeat occurrence; shared by `AlertCard` and `AlertSummary` |
| `AlertSummary` | Custom | Top of the alert detail: the alert as a 16 px-padded card with `AlertStatusBar`, the title as the page's `h1`, fields in Geist Mono, then first and last seen, team, escalated teams, who acknowledged and who resolved ("PagerCutie, automatically" for `Resolution.auto`); **Acknowledge** / **Resolve** as on the card |
| `DeliveryTable` | `Table` | One row per recipient and channel: name (or "You", or `User 0193c111` in Geist Mono when no loaded list names them), channel icon and label, `DeliveryStatusLine`, attempts, last error in alert red ("None" muted), **Show message** / **Hide message** opening the rendered message under the row; skeleton rows while loading; `EmptyState` "Nobody was notified" |
| `AlertHistory` | Custom | Timeline of audit entries, newest first: a hollow dot on a vertical line, actor ("System" for the pipeline) and the action in plain words, `RelativeTime` on the right; `EmptyState` "No history yet" |
| `ParsedStepList` | Custom | A runbook's steps before any run (no §5.3 states): number in Geist Mono, action icon and label, what it does and whether it needs approval in one muted line, parameters with `{{…}}` placeholders on a muted chip in Geist Mono, the step's question and guard as sentences; **Needs approval** badge in `--primary` on `--accent` when the step or its action's default requires it (ADR-0071) |
| `ParsePreview` | Custom | Next to the runbook text, bordered panel: empty ("Paste a runbook or insert an example…"), loading (three skeleton bars), parsed (warnings box, `ParsedStepList`, "Applies when" condition as a sentence with the JSON behind **Show as JSON**), invalid (`422` messages in alert red, `role="alert"`), failed (message, `role="alert"`); "Updating preview…" in a `role="status"` line while a newer text waits; debounced 400 ms |
| `RunbookEditor` | Custom, react-hook-form | Title; slug that follows the title until edited and is read-only once saved; format `SegmentedControl` (YAML, Markdown, Free text, Link) with a hint per format; runbook text in a Geist Mono textarea with **Insert example** (the three REQUIREMENTS.md §6.2 samples; asks before replacing text the user wrote); `ParsePreview` beside it from 1024 px, below it on narrow screens; **Save runbook** disabled while unchanged on an existing runbook; **Delete runbook** with `ConfirmDialog`; "Leave without saving?" dialog on navigation with unsaved changes; viewers get the saved text and steps read-only |
| `Textarea` | Base UI Field control | Multi-line `Input`: same border, radius, focus ring and invalid state; label, helper and error come from the surrounding `Field` |
| `CopyButton` | `Button` ghost icon | Copies a value; the icon turns into a check ("Copied") or a cross ("Couldn't copy. Select the text and copy it.") for 2 s, announced through a status region; `aria-label` names what is copied |
| `SourceFields` | `Field`, `Select`, `Switch` | Source form: name, slug (follows the name until edited) and type on create only; one muted line saying each event is checked against the latest version of each of the team's event schemas and the most specific match wins, with a link to the team's **event schemas** (sources carry no schema setting, ADR-0065); severity field, value → severity rows and default; **Accept events**. Field errors under each control, list errors under the rows |
| `TokenReveal` | Custom | Shown once after a token is created or rotated: "This token is shown only once.", the token in a read-only Geist Mono field with **Copy token**, and a ready-to-paste command per source type with **Copy command**; the token leaves memory when the dialog closes (ADR-0072). The sources table's **Token** column says "Set", or "No token yet" in muted text with **Create token** for editors (`SourceRead.has_token`); the row menu offers **Create token** or **Rotate token** to match |
| `JsonEditor` | `Textarea` | Geist Mono, 13 / 20, no spell check; the parse error under it as "Line 3, column 17: Expected a value…", or a server error on the same field |
| `FieldTree` | Custom | Fields of a JSON Schema, nested with a left rule: name in Geist Mono (path in the title), type badges, "required" in `--primary`, constraints in plain words ("at most 3 characters", "one of "TIMEOUT", "REJECTED""), "one of"/"any of" above alternatives, notes for recursive and external `$ref`s; empty: "No fields yet." |
| `SchemaBuilder` | `@dnd-kit/core`, `FieldRow` | **Builder** mode of the new event schema page, next to the generated JSON Schema (Geist Mono, read-only). Palette of types (icon in `--primary`, label) to drag into the fields or click to add at the end; the payload as a 12 px panel with **Only listed fields** and **Add field**; drop slots between fields show a violet line with a ring at its start, an empty object shows a dashed "No fields yet. Drag a type here or add a field." that turns violet under the pointer; the dragged field stays in place at 40 % opacity and a preview card follows the pointer. A schema the builder can't show opens as JSON, and the builder lists each part ("top level: Uses $defs.") with **Edit as JSON** (ADR-0080) |
| `FieldRow` | `Input`, `Select`, `Switch`, `DropdownMenu` | One field as an 8 px-radius card: grip handle, type icon, name in Geist Mono, type picker, **Required** / **Optional** switch (label in `--primary` when required), **Constraints** toggle with a count badge, actions menu (move up, down, into the object above, out of the parent, remove). Collapsed: constraints in plain words under the name; open: description, "Can be null" and the type's constraints on a muted band. Objects nest their fields behind a 2 px left rule with **Add field**; lists show "Each item is" with its own type and constraints; fixed values show "Always this value" / "One of these values" as typed chips. Errors in alert red under the name or the constraint. Rows move with `spring` and leave with `exit` |
| `SampleCheck` | `JsonEditor`, `Button` | Sample payload and **Check sample**; result in a polite status region: check icon and "The sample matches the schema.", or a cross and each problem as JSON pointer (Geist Mono, alert red text) and message; parse errors inline before any request; a failed check shows its reason in alert red |
| `ConditionEditor` | Custom | Rule condition as nested AND / OR groups (two levels) of predicates; each predicate: field (`FieldPathInput`), operator from the field's type in plain words ("is more than", "matches the pattern"), value by operator (text, number, yes / no, severity, a list of chips for "is one of"); **Not** on any group or predicate; **Add condition**, **Add group**, remove; errors under the predicate's field or value, from the client or a `422`; the whole condition as one sentence underneath ("type is WORKFLOW_FAILED and environment is prod"); read-only: controls disabled, no add or remove (ADR-0070) |
| `FieldPathInput` | Base UI Autocomplete | Free text in Geist Mono with suggestions (path and type) from the picked event schemas and the event metadata; any typed path is kept (`RUL-1`); "No known field matches. You can still use the path you typed." when nothing matches |
| `PathListInput` | `FieldPathInput` | Ordered field paths as removable chips plus an input and **Add** (Enter adds); rejects a path the API would reject; **Add** turns off at the limit and says why |
| `RecipientsEditor` | Custom | Recipients in words with remove buttons; add an on-call person of a team, everyone in a team or one person (`Combobox` over `GET /users`); switch "Use each person's notification settings" or a channel `ToggleGroup`; a personal rule shows "This rule notifies only you." |
| `RuleTestPanel` | Custom | Sample payload JSON, source and severity; checks the draft against `POST /rules/test` 400 ms after the last change; states: paste a sample, finish the condition, invalid JSON (under the field), testing, matches, doesn't match, error in alert red |
| `RulePreview` | `AlertCard` | The alert the rule would raise in its colour, open, without actions, title, body and fields filled from the sample event; unresolved placeholders stay as written |

### Live connection

The feed shows its connection state (`UI-1`, ADR-0012). Connected shows nothing. Reconnecting shows a thin bar
under the header with "Reconnecting…" in muted text. Offline for more than 10 s shows "Live updates paused" and a
**Retry** button, and the feed stays readable.

### Screen readers

New critical and error alerts are announced through an `aria-live="assertive"` region ("Critical: Settlement
wf-8f21 failed at reserve-funds"); other severities use `polite`. Counter bumps are not announced.

## 10. Writing in the UI

- Plain words for non-engineers (`UI-6`): "Acknowledge" with a tooltip "Tell your team you are on it", not
  "ACK".
- Sentence case for every label, title and button.
- Buttons say what happens: **Acknowledge**, **Resolve**, **Approve step**, **Save rule**. One label per action
  across the app.
- Numbers use grouping (`12,400,000`), currency codes stay as the event sends them (`USD`).
- No em dashes in UI copy.
- Errors say what went wrong and what to do next: "Couldn't save the rule. The condition needs at least one
  field."

## 11. Changing the system

- **New colour or severity in the backend.** Run `mise run api`; `tsc` then lists every map in §4.3 that needs a
  new entry. Add the tokens to `index.css` in both themes, then re-check contrast (§4.4).
- **New token or component.** Add it here in the same change, with both themes.
- **A decision that changes this document's rules** (a new library, a different theme model) gets an ADR, as in
  [AGENTS.md](../AGENTS.md).

## 12. Brand

The mark is a pager whose screen shows a face, on a violet tile. The logo is the mark with the wordmark
"PagerCutie" to its right. Decisions are in [ADR-0040](decisions/0040-logo-and-icon.md).

| File | Contents | Use |
|---|---|---|
| `frontend/public/favicon.svg` | Mark | Browser tab (`index.html`) |
| `frontend/src/assets/brand/icon.svg` | Mark | Anywhere the mark stands alone; same on both themes |
| `frontend/src/assets/brand/logo-light.svg` | Logo, dark wordmark | Light theme, README on light backgrounds |
| `frontend/src/assets/brand/logo-dark.svg` | Logo, light wordmark | Dark theme |

In the app, use `Logo` and `LogoMark` from `frontend/src/components/brand/Logo.tsx` instead of the files. They
render inline SVG; the wordmark fills with `currentColor`, so it follows `data-theme` with no second file. Each
shape carries a class (`logo-tile`, `logo-body`, `logo-screen`, `logo-eye`, `logo-smile`, `logo-wordmark`) for
animation. The SVG files are for places outside the app, such as the README; there, pick the file by background.
The component, the files and the splash in `frontend/index.html` (§12.1) hold the same paths, so change all three
together.

**Construction.** 64-unit grid. Tile radius 15. Pager body 46 × 36 at (9, 14), radius 10, centred on the tile.
Screen 34 × 24 at (15, 20), inset 6 from the body, radius 4 so its corners are concentric with the body's. Eyes
are circles of radius 3.2 at (25, 28.6) and (39, 28.6); the smile is a 3-unit round-capped stroke from
(27.5, 35.6) to (36.5, 35.6) through control point (32, 39.4). The face is centred in the screen within 0.2 units
and keeps at least 2.7 units between the eyes and the smile. When animating the face, move eyes and smile
together (`logo-face`) so that gap holds. The mark is drawn by hand; the §2 rule against hand-drawn paths covers UI icons, not the brand mark.

**Colour.** sRGB hex, because favicon renderers and GitHub do not support `oklch()`.

| Part | Token | Value |
|---|---|---|
| Tile, screen | light `--primary` on both themes | `#6d4ae4` (`oklch(0.54 0.22 287)`) |
| Body, face | light `--primary-foreground` | `#fbfbfe` (`oklch(0.99 0.004 287)`) |
| Wordmark, light theme | light `--foreground` | `#171721` (`oklch(0.21 0.02 285)`) |
| Wordmark, dark theme | dark `--foreground` | `#f3f3f7` (`oklch(0.965 0.005 285)`) |

The wordmark is one colour; violet stays in the mark (§4.1). No alert colour appears in the brand (§1).

**Wordmark.** Geist SemiBold (600, the page-title weight from §6) from the `geist` npm package 1.9.2, tracking
-0.02em, shaped with HarfBuzz so kerning applies, and converted to outlines so it renders without the font. At
40-unit font size the cap height is 28.4. In the logo the mark is 40 × 40, the gap is 12, and the cap height is
centred on the mark.

**Sizes.** The mark works down to 16 px, where the face drops out and a framed screen remains. Keep clear space
around the logo of at least a quarter of the mark's height. Do not recolour, stretch or add effects.

### 12.1 Splash

`frontend/index.html` holds a splash inside `#root`: a static copy of the `Logo` markup at 48 px high, with inline
CSS. React's first `root.render` replaces everything inside `#root`, so the splash disappears the moment the app
mounts, mid-animation or not, with no removal code and no exit fade. It covers only the bundle download; data
loading after mount uses skeletons (§9). Decisions are in
[ADR-0041](decisions/0041-splash-screen-in-index-html.md).

The splash stays hidden for the first 300 ms, so a fast load shows nothing. Then it plays "Power on". Times are
from the moment it appears (add 300 ms for time since page load); the curve is `fast`/`base`'s
`cubic-bezier(0.2, 0.8, 0.2, 1)`.

| Part (class) | Start | Length | Animation |
|---|---|---|---|
| Mark (`logo-mark`) | 0 ms | 150 ms | Fades in |
| Screen (`logo-screen`) | 100 ms | 300 ms | Lights from `#2b2150` to the tile violet |
| First eye, second eye (`logo-eye`) | 350 ms, 410 ms | 250 ms | Scale from 0 |
| Smile (`logo-smile`) | 500 ms | 250 ms | Draws left to right (stroke dash); hidden until it starts |
| Wordmark (`logo-wordmark`) | 600 ms | 300 ms | Wipes in left to right (`clip-path`) |
| Face (`logo-face`) | 1600 ms | 3.2 s, repeating | Glances 2 units left, then right; eyes and smile move together |

- `transform-box: fill-box` goes on `logo-eye` and `logo-face` only. `logo-mark` and `logo-wordmark` carry
  `transform` attributes, and `fill-box` would move them.
- Under `prefers-reduced-motion: reduce` the logo appears after 300 ms without moving.
- After 10 s a muted line, "Still loading. Reload the page if nothing changes.", appears under the logo, so a
  bundle that never loads does not leave a silent screen.
- Colours are hex. Background and wordmark follow `data-theme` when it is set and `prefers-color-scheme`
  otherwise, until the theme script from §3 exists.
- The container has `role="status"` and `aria-label="Loading PagerCutie"`; the SVG is `aria-hidden`.
