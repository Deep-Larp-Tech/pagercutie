import { createFileRoute } from '@tanstack/react-router'
import { AuditLogPage } from '@/components/audit/audit-log'
import { auditSearch } from '@/lib/audit'

export const Route = createFileRoute('/_app/admin/audit')({
  staticData: { title: 'Audit log' },
  validateSearch: auditSearch,
  component: AdminAuditPage,
})

/** Every team's audit log, for admins (DOMAIN.md §4). */
function AdminAuditPage() {
  const filters = Route.useSearch()
  const navigate = Route.useNavigate()
  return <AuditLogPage filters={filters} onFiltersChange={(next) => void navigate({ search: next })} />
}
