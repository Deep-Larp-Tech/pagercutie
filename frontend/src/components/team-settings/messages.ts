/** A save answered `403`: the user is not a lead (or admin) of the team. */
export const SAVE_FORBIDDEN = 'Only team leads can change this.'

/** A save answered `400` or a `422` without field errors. */
export const SAVE_REJECTED = "Couldn't save the changes. Reload the page and try again."

/** The team answered `404`: deleted, or no longer visible to the user. */
export const TEAM_GONE = 'This team no longer exists. Pick another team from the switcher.'

/** No answer at all (network error). */
export const OFFLINE = "Couldn't reach PagerCutie. Check your connection and try again."

/** A `GET` answered `422`, which only a malformed id in the URL causes. */
export const LOAD_REJECTED = "Couldn't load this page. Reload it and try again."
