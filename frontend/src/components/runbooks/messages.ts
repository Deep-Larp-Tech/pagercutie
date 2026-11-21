/** Shown once at the top of a runbook page to viewers. */
export const READ_ONLY = 'Only members and leads can change runbooks.'

/** A save answered `403`. */
export const SAVE_FORBIDDEN = "You can't change this team's runbooks. Ask a team lead to make you a member."

/** A save answered `400` or a `422` without field errors. */
export const SAVE_REJECTED = "Couldn't save the runbook. Reload the page and try again."

/** The runbook answered `404`: deleted, or no longer visible to the user. */
export const RUNBOOK_GONE = 'This runbook no longer exists. Go back to the runbook list.'

/** A `GET` answered `422`, which only a malformed id in the URL causes. */
export const LOAD_REJECTED = "Couldn't load this runbook. Check the link and try again."

/** Shown when a slug does not match the slug pattern (DOMAIN.md §1). */
export const SLUG_INVALID = 'Use lower case letters and digits, joined by single hyphens, at most 50 characters.'
