import type { AuditEntryRead } from '@/api/generated/model'
import { RelativeTime } from '@/components/alerts/relative-time'
import { usePersonName } from '@/hooks/use-person-name'
import { auditActionText } from '@/lib/audit'
import { useMe } from '@/lib/session'
import { PersonNameText } from './person-name'

/** Props for `AlertHistory`. */
export interface AlertHistoryProps {
  /** The alert's audit entries, newest first as `GET /audit` answers. */
  entries: readonly AuditEntryRead[]
}

/** What was done to an alert and by whom (`RUN-5`): a timeline of its audit entries, "System" for the pipeline. */
export function AlertHistory({ entries }: AlertHistoryProps) {
  const me = useMe()
  const personName = usePersonName()
  return (
    <ol aria-label="History" className="flex flex-col">
      {entries.map((entry) => (
        <li key={entry.id} className="relative flex gap-3 pb-4 last:pb-0">
          <span aria-hidden className="relative flex w-2.5 shrink-0 justify-center">
            <span className="absolute top-4 bottom-[-4px] w-px bg-border [li:last-child_&]:hidden" />
            <span className="mt-1.5 size-2.5 rounded-full border-2 border-muted-foreground/60 bg-background" />
          </span>
          <div className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
            <p>
              <span className="font-medium">
                {entry.actor_user_id === null ? 'System' : <PersonNameText person={personName(entry.actor_user_id)} />}
              </span>
              <span className="text-muted-foreground">: {auditActionText(entry.action)}</span>
            </p>
            <RelativeTime value={entry.at} timeZone={me.user.timezone} />
          </div>
        </li>
      ))}
    </ol>
  )
}
