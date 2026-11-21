import type { RuleScope } from './rule-scope'

/** No answer at all (network error). */
export const OFFLINE = "Couldn't reach PagerCutie. Check your connection and try again."

/** A request answered `400`: the body could not be decoded. */
export const BODY_UNREADABLE = "Couldn't read the rule. Reload the page and try again."

/** A `GET` answered `422`, which only a malformed id in the URL causes. */
export const LOAD_REJECTED = "Couldn't load this rule. Check the link and try again."

/** A rule answered `404`: deleted, or not visible to the user. */
export const RULE_GONE = "This rule doesn't exist anymore. It may have been deleted."

/** The line read-only users see once at the top, and the message of a `403`. */
export function forbiddenMessage(scope: RuleScope): string {
  return scope.kind === 'team'
    ? 'Only members and leads of this team can change its rules.'
    : 'Only the owner can change a personal rule.'
}
