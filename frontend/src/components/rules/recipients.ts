import type { Recipient, UserRead } from '@/api/generated/model'
import type { VisibleTeam } from '@/lib/teams'

/** What a recipient type means, as a picker option. */
export const recipientTypeLabel = {
  on_call: 'On-call person of a team',
  team: 'Everyone in a team',
  user: 'One person',
} as const satisfies Record<Recipient['type'], string>

/** Names to show recipients by: the teams the user can open and the people `GET /users` returned. */
export interface RecipientNames {
  teams: readonly VisibleTeam[]
  users: readonly UserRead[]
  /** The signed-in user, shown as "You". */
  meId: string
}

function teamName(names: RecipientNames, teamId: string): string {
  return names.teams.find(({ team }) => team.id === teamId)?.team.name ?? 'another team'
}

/** One recipient in words: "On call in Settlements", "Everyone in Rates", "Bob Novak". */
export function describeRecipient(recipient: Recipient, names: RecipientNames): string {
  switch (recipient.type) {
    case 'on_call':
      return `On call in ${teamName(names, recipient.team_id)}`
    case 'team':
      return `Everyone in ${teamName(names, recipient.team_id)}`
    case 'user':
      if (recipient.user_id === names.meId) return 'You'
      return names.users.find((user) => user.id === recipient.user_id)?.display_name ?? 'One person'
    default:
      return recipient satisfies never
  }
}

/** Recipients in words, comma separated. */
export function describeRecipients(recipients: readonly Recipient[], names: RecipientNames): string {
  return recipients.map((recipient) => describeRecipient(recipient, names)).join(', ')
}

/** Whether two recipients name the same people. */
export function sameRecipient(a: Recipient, b: Recipient): boolean {
  if (a.type === 'user' || b.type === 'user') return a.type === 'user' && b.type === 'user' && a.user_id === b.user_id
  return a.type === b.type && a.team_id === b.team_id
}
