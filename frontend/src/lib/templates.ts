import { formatFieldValue } from './fields'

/** A `{{field.path}}` placeholder; spaces inside the braces are allowed. */
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
 * A runbook step's `template` filled from the alert's first event (SPEC §11.2): `{{payload.workflowId}}` and the
 * brief's short form `{{workflowId}}` both read `payload.workflowId`; numbers are grouped for reading. A placeholder
 * the payload has no value for stays as written, so the reader sees what is missing.
 */
export function renderTemplate(template: string, payload: Record<string, unknown>): string {
  return template.replaceAll(PLACEHOLDER, (placeholder, path: string) => {
    const value = path.startsWith('payload.') ? lookupPath(payload, path.slice('payload.'.length)) : lookupPath(payload, path)
    return value === undefined ? placeholder : formatFieldValue(value)
  })
}

/**
 * A rule's title or body template (`RUL-4`) filled from a whole event (`{source, severity, schema_id, payload}`), as
 * the API renders it: paths start at the event, values print as sent. A placeholder the event has no value for stays
 * as written, so the author sees which one did not resolve.
 */
export function renderEventTemplate(template: string, event: unknown): string {
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
