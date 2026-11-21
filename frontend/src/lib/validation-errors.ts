import type { HTTPValidationError } from '@/api/generated/model'

/** One FastAPI `422` error in the request body: where it is below `body`, and the message. */
export interface BodyIssue {
  /** Path below `body`, e.g. `['rules', 0, 'channels']`; empty for the body itself. */
  path: readonly (string | number)[]
  message: string
}

/** The errors of a `422` answer that point into the request body; path and query errors are dropped. */
export function bodyIssues(error: HTTPValidationError): BodyIssue[] {
  return (error.detail ?? [])
    .filter(({ loc }) => loc[0] === 'body')
    .map(({ loc, msg }) => ({ path: loc.slice(1), message: msg }))
}
