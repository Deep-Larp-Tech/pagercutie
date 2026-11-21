import { http, passthrough } from 'msw'
import { getStreamAlertsUrl } from '@/api/generated/alerts/alerts'
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

const bypass = http.all('*', ({ request }) => {
  const { pathname } = new URL(request.url)
  return pathname.startsWith('/api/') && pathname !== getStreamAlertsUrl() ? undefined : passthrough()
})

/** Every generated faker handler, one per endpoint, behind `bypass`; responses are random on each request. */
export const handlers = [
  bypass,
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
