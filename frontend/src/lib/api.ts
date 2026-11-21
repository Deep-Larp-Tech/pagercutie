/**
 * Message for a response whose status the contract does not document (a `501` stub, a `502` from the proxy).
 *
 * Call it in the `default` branch of a `switch` on a generated response's `status`. The parameter is `never`, so
 * `tsc` also fails when a documented status has no `case` (ADR-0045).
 */
export function unexpectedStatusMessage(response: never): string {
  const value: unknown = response
  const status =
    typeof value === 'object' && value !== null && 'status' in value && typeof value.status === 'number'
      ? value.status
      : null
  if (status === 501) return "This feature isn't available yet."
  if (status === null) return 'Something went wrong. Try again in a moment.'
  return `Something went wrong on the server (HTTP ${status}). Try again in a moment.`
}

/** Thrown where a route cannot render a response; its message comes from `unexpectedStatusMessage`. */
export class UnexpectedStatusError extends Error {
  override name = 'UnexpectedStatusError'
}
