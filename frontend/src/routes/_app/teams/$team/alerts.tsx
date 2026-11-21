import { createFileRoute, Link } from '@tanstack/react-router'
import { ListFilter } from 'lucide-react'
import * as zod from 'zod'
import { AlertStatus, Severity } from '@/api/generated/model'
import { FeedFilters } from '@/components/alerts/feed-filters'
import { LiveAlertFeed } from '@/components/alerts/live-alert-feed'
import { PageHeader } from '@/components/shell/page-header'
import { buttonVariants } from '@/components/ui/styles'
import type { AlertFilters } from '@/lib/alert-feed'

/** Status filter while the address names none: the alerts someone still has to work on. */
const DEFAULT_STATUS = [AlertStatus.open, AlertStatus.acknowledged] as const satisfies readonly AlertStatus[]

/** Feed filters in the address; a hand-edited value that does not parse falls back to the default feed. */
const feedSearch = zod.object({
  /** Statuses to show; absent means `DEFAULT_STATUS`, empty means every status. */
  status: zod.array(zod.enum(AlertStatus)).optional().catch(undefined),
  /** Severities to show; absent or empty means every severity. */
  severity: zod.array(zod.enum(Severity)).optional().catch(undefined),
})

type FeedSearch = zod.infer<typeof feedSearch>

function sameSet(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((value) => b.includes(value))
}

/** The search params for `filters`, leaving out values that equal the default so the plain URL stays plain. */
function toSearch({ status, severity }: AlertFilters): FeedSearch {
  return {
    status: status === undefined || sameSet(status, DEFAULT_STATUS) ? undefined : [...status],
    severity: severity === undefined || severity.length === 0 ? undefined : [...severity],
  }
}

export const Route = createFileRoute('/_app/teams/$team/alerts')({
  staticData: { title: 'Alerts' },
  validateSearch: feedSearch,
  component: TeamAlertsPage,
})

/** The team's live feed (`UI-1`, `UI-2`) with status and severity filters. */
function TeamAlertsPage() {
  const team = Route.useRouteContext({ select: (context) => context.team })
  const search = Route.useSearch()
  const navigate = Route.useNavigate()
  const filters: AlertFilters = { status: search.status ?? DEFAULT_STATUS, severity: search.severity }
  const filtered = search.status !== undefined || search.severity !== undefined

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Alerts" description={`Live alerts from ${team.name}'s rules.`} />
      <section className="flex flex-col gap-4">
        <h2 className="sr-only">Live feed</h2>
        <FeedFilters
          value={filters}
          onChange={(next) => void navigate({ search: toSearch(next), replace: true })}
        />
        <LiveAlertFeed
          teamId={team.id}
          filters={filters}
          empty={
            filtered
              ? {
                  icon: ListFilter,
                  title: 'No alerts match these filters',
                  description: 'Change the filters above to see more alerts.',
                  action: (
                    <Link to="." search={{}} replace className={buttonVariants({ variant: 'secondary' })}>
                      Clear filters
                    </Link>
                  ),
                }
              : {
                  title: 'No open alerts',
                  description: "Alerts from this team's rules show up here the moment they fire.",
                  action: (
                    <Link
                      to="/teams/$team/rules"
                      params={{ team: team.slug }}
                      className={buttonVariants({ variant: 'secondary' })}
                    >
                      Open rules
                    </Link>
                  ),
                }
          }
        />
      </section>
    </div>
  )
}
