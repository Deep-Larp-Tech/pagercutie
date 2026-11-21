import { createFileRoute } from '@tanstack/react-router'
import { AuditLogPage } from '@/components/audit/audit-log'
import { auditSearch } from '@/lib/audit'

export const Route = createFileRoute('/_app/teams/$team/audit')({
  staticData: { title: 'Audit log' },
  validateSearch: auditSearch,
  component: TeamAuditPage,
})

/** The team's audit log; every team role may read it (DOMAIN.md §4), so the team layout's check is enough. */
function TeamAuditPage() {
  const team = Route.useRouteContext({ select: (context) => context.team })
  const filters = Route.useSearch()
  const navigate = Route.useNavigate()
  return <AuditLogPage team={team} filters={filters} onFiltersChange={(next) => void navigate({ search: next })} />
}
