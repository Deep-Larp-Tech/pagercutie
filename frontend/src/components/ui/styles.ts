/** Focus ring on every interactive control: 2 px `--ring` with a 2 px gap (DESIGN.md §4.1). */
export const focusRing =
  'outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background'

/** Colour transition for hover and press (`fast`, DESIGN.md §8). */
export const controlTransition =
  'transition-[color,background-color,border-color,box-shadow,scale,translate] duration-(--duration-fast) ease-standard'

/** Open and close animation for popovers, menus, tooltips and dialogs: fade and scale from 0.97 (DESIGN.md §8). */
export const layerMotion =
  'origin-(--transform-origin) data-open:animate-in data-open:fade-in-0 data-open:zoom-in-97 data-open:duration-(--duration-base) data-open:ease-standard data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-97 data-closed:duration-(--duration-exit) data-closed:ease-exit'

/** Surface of a floating layer: popover colours, 14 px radius, border and popover shadow (DESIGN.md §7). */
export const layerSurface = 'rounded-xl border bg-popover text-popover-foreground shadow-popover'

/** Item inside a menu or select list; highlighted by pointer or keyboard. */
export const listItem =
  'relative flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:size-4 [&_svg]:text-muted-foreground'

/** Shared look of text inputs and select triggers: 32 px tall, 8 px radius, `--input` border. */
export const fieldControl =
  'h-8 w-full min-w-0 rounded-md border border-input bg-transparent px-2.5 text-sm placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-alert-red aria-invalid:focus-visible:ring-alert-red'
