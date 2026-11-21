import { useGetTeamOnCall } from '@/api/generated/teams/teams'
import type { MeRead, OnCallRead, TeamRead } from '@/api/generated/model'
import { Skeleton } from '@/components/ui/skeleton'
import { unexpectedStatusMessage } from '@/lib/api'
import { useMe } from '@/lib/session'
import { weekdayTime } from '@/lib/time'
import { cn } from '@/lib/utils'

/** The sentence an on-call answer reads as, with shift ends in the signed-in user's time zone. */
function onCallSentence(onCall: OnCallRead, me: MeRead): string {
  if (onCall.user === null) return 'No rotation set'
  if (onCall.user.id !== me.user.id) return `${onCall.user.display_name} is on call`
  return onCall.until === null
    ? "You're on call"
    : `You're on call until ${weekdayTime(onCall.until, me.user.timezone)}`
}

/** Props for `OnCallCard`. */
export interface OnCallCardProps {
  team: TeamRead
}

/** Who is on call for one team (`GET /teams/{id}/on-call`, DOMAIN.md §5): you, someone else, or no rotation. */
export function OnCallCard({ team }: OnCallCardProps) {
  const me = useMe()
  const { data, isPending, isError } = useGetTeamOnCall(team.id)

  let content
  let failed = false
  if (isPending) {
    content = <Skeleton className="h-5 w-40" />
  } else if (isError) {
    failed = true
    content = "Couldn't load who is on call. Check your connection."
  } else {
    switch (data.status) {
      case 200:
        content = onCallSentence(data.data, me)
        break
      case 401:
        content = null
        break
      case 404:
        failed = true
        content = "Couldn't find this team's rotation."
        break
      case 422:
        failed = true
        content = "Couldn't load who is on call."
        break
      default:
        failed = true
        content = unexpectedStatusMessage(data)
    }
  }

  return (
    <section
      aria-label={`On call for ${team.name}`}
      className="flex flex-col gap-1 rounded-lg border px-4 py-3"
    >
      <h3 className="text-[12px]/[16px] font-medium text-muted-foreground">{team.name}</h3>
      <div
        role={failed ? 'alert' : undefined}
        className={cn('font-medium', failed && 'font-normal text-muted-foreground')}
      >
        {content}
      </div>
    </section>
  )
}
