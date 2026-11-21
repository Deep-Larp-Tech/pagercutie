/** A field value as an alert shows it: strings as sent, numbers grouped (DESIGN.md §10), anything else as JSON. */
export function formatFieldValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return value.toLocaleString('en')
  return JSON.stringify(value) ?? String(value)
}
