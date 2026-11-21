import { formatFieldValue } from './fields'

/** A `{{field.path}}` placeholder; spaces inside the braces are allowed. */
const placeholder = /\{\{\s*([^{}\s]+)\s*\}\}/g

function lookup(root: unknown, path: readonly string[]): unknown {
  let value = root
  for (const key of path) {
    if (typeof value !== 'object' || value === null || !(key in value)) return undefined
    value = Object.entries(value).find(([name]) => name === key)?.[1]
  }
  return value
}

/**
 * `template` with each `{{field.path}}` filled from the alert's first event (SPEC §11.2): `{{payload.workflowId}}`
 * and the brief's short form `{{workflowId}}` both read `payload.workflowId`. A placeholder the payload has no value
 * for stays as written, so the reader sees what is missing.
 */
export function renderTemplate(template: string, payload: Record<string, unknown>): string {
  return template.replace(placeholder, (match, path: string) => {
    const keys = path.split('.')
    const value = keys[0] === 'payload' ? lookup(payload, keys.slice(1)) : lookup(payload, keys)
    return value === undefined ? match : formatFieldValue(value)
  })
}
