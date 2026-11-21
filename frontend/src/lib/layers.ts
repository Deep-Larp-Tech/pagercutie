/** Z-index scale (DESIGN.md §7); higher layers stack above lower ones. */
export const layers = {
  header: 10,
  drawer: 30,
  popover: 40,
  dialog: 50,
  toast: 60,
} as const satisfies Record<string, number>
