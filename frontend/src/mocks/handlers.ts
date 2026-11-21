import { http, passthrough } from 'msw'
import { getAlertsMock } from '@/api/generated/alerts/alerts.msw'
import { getAuditMock } from '@/api/generated/audit/audit.msw'
import { getAuthMock } from '@/api/generated/auth/auth.msw'
import { getEventSchemasMock } from '@/api/generated/event-schemas/event-schemas.msw'
import { getHealthMock } from '@/api/generated/health/health.msw'
import { getRulesMock } from '@/api/generated/rules/rules.msw'
import { getRunbooksMock } from '@/api/generated/runbooks/runbooks.msw'
import { getSourcesMock } from '@/api/generated/sources/sources.msw'
import { getTeamsMock } from '@/api/generated/teams/teams.msw'
import { getUsersMock } from '@/api/generated/users/users.msw'

/**
 * Lets every request outside `/api` through. The generated paths start with a wildcard and would otherwise also match pages and
 * Vite modules such as `/admin/users` and `/src/api/generated/users/users.ts`.
 */
const apiOnly = http.all('*', ({ request }) =>
  new URL(request.url).pathname.startsWith('/api/') ? undefined : passthrough(),
)

/** Every generated faker handler, one per endpoint, behind `apiOnly`; responses are random on each request. */
export const handlers = [
  apiOnly,
  ...getAlertsMock(),
  ...getAuditMock(),
  ...getAuthMock(),
  ...getEventSchemasMock(),
  ...getHealthMock(),
  ...getRulesMock(),
  ...getRunbooksMock(),
  ...getSourcesMock(),
  ...getTeamsMock(),
  ...getUsersMock(),
]
