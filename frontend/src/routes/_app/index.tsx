import { createFileRoute, Link } from '@tanstack/react-router'
import { AlertStatus } from '@/api/generated/model'
import { LiveAlertFeed } from '@/components/alerts/live-alert-feed'
import { OnCallCard } from '@/components/alerts/on-call-card'
import { PageHeader } from '@/components/shell/page-header'
import { buttonVariants } from '@/components/ui/styles'
import { useVisibleTeams } from '@/hooks/use-visible-teams'
import type { AlertFilters } from '@/lib/alert-feed'
import { useMe } from '@/lib/session'

export const Route = createFileRoute('/_app/')({
  staticData: { title: 'Overview' },
  component: OverviewPage,
})

/** The Overview shows alerts that still need someone, across every team and personal rule. */
const overviewFilters = {
  status: [AlertStatus.open, AlertStatus.acknowledged],
} as const satisfies AlertFilters

const sectionTitle = 'text-[18px]/[26px] font-semibold tracking-[-0.01em]'

/** `/`: who is on call in each of the user's teams, then one live feed of their open and acknowledged alerts. */
function OverviewPage() {
  const me = useMe()
  const { current } = useVisibleTeams()
  const teamNames = new Map(me.memberships.map(({ team }) => [team.id, team.name]))

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Overview"
        description="Who is on call in your teams, and the alerts that still need someone."
      />
      {me.memberships.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className={sectionTitle}>On call</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {me.memberships.map(({ team }) => (
              <OnCallCard key={team.id} team={team} />
            ))}
          </div>
        </section>
      )}
      <section className="flex flex-col gap-3">
        <h2 className={sectionTitle}>Open alerts</h2>
        <LiveAlertFeed
          filters={overviewFilters}
          teamName={(alert) => (alert.team_id === null ? 'Personal rule' : teamNames.get(alert.team_id))}
          empty={{
            title: 'Nothing needs you right now',
            description: 'Open and acknowledged alerts from your teams and personal rules show up here.',
            action:
              current === undefined ? undefined : (
                <Link
                  to="/teams/$team/rules"
                  params={{ team: current.team.slug }}
                  className={buttonVariants({ variant: 'secondary' })}
                >
                  Open {current.team.name} rules
                </Link>
              ),
          }}
        />
      </section>
    </div>
  )
}
