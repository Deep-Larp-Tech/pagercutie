/** A `{{field.path}}` placeholder in a rule's title or body template (`RUL-4`). */
const PLACEHOLDER = /\{\{\s*([A-Za-z_]\w*(?:\.\w+)*)\s*\}\}/g

/** The value at a dot path in a JSON value, or `undefined` when the path leads nowhere. */
export function lookupPath(value: unknown, path: string): unknown {
  let current = value
  for (const part of path.split('.')) {
    if (typeof current !== 'object' || current === null) return undefined
    current = Object.entries(current).find(([key]) => key === part)?.[1]
  }
  return current
}

/** A looked-up value as template text: strings as sent, anything else as JSON. */
export function valueText(value: unknown): string {
  return typeof value === 'string' ? value : (JSON.stringify(value) ?? String(value))
}

/**
 * The template with each placeholder replaced from `event` (`{source, severity, schema_id, payload}`). A placeholder
 * the event has no value for stays as written, so the author sees which one did not resolve.
 */
export function renderTemplate(template: string, event: unknown): string {
  return template.replaceAll(PLACEHOLDER, (placeholder, path: string) => {
    const value = lookupPath(event, path)
    return value === undefined ? placeholder : valueText(value)
  })
}

/** The template with `{{path}}` inserted at `position` (a selection start), or at the end without one. */
export function insertPlaceholder(template: string, path: string, position: number | null): { text: string; caret: number } {
  const at = position === null ? template.length : Math.min(position, template.length)
  const placeholder = `{{${path}}}`
  return { text: template.slice(0, at) + placeholder + template.slice(at), caret: at + placeholder.length }
}
