import { delay, http, HttpResponse } from 'msw'
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import {
  acknowledgeAlert,
  getAcknowledgeAlertUrl,
  getAlert,
  getRunbookRun,
  getGetRunbookRunUrl,
  getGetAlertUrl,
  getListAlertDeliveriesUrl,
  getListAlertsUrl,
  listAlertDeliveries,
  listAlerts,
} from '@/api/generated/alerts/alerts'
import { getListAuditEntriesUrl, listAuditEntries } from '@/api/generated/audit/audit'
import type { MeRead, RuleRead, TeamRole } from '@/api/generated/model'
import { getGetRuleUrl, getListRulesUrl, getRule, listRules } from '@/api/generated/rules/rules'
import { getListRunbooksUrl, listRunbooks } from '@/api/generated/runbooks/runbooks'
import { getListTeamsUrl, listTeams } from '@/api/generated/teams/teams'
import { alert, quietFeedEndpoints } from '@/test/alerts'
import { respond } from '@/test/http'
import { withBuilderData } from '@/test/rules'
import { membership, petra } from '@/test/people'
import { server } from '@/test/server'
import { openAs, recordRequests, settlements } from '@/test/teams'

beforeAll(() => {
  Element.prototype.scrollIntoView = () => {}
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
})

beforeEach(() => {
  server.use(
    ...quietFeedEndpoints(),
    respond(listRules, 'get', getListRulesUrl(), 200, []),
    respond(listRunbooks, 'get', getListRunbooksUrl(), 200, []),
    respond(listTeams, 'get', getListTeamsUrl(), 200, [settlements]),
  )
})

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  delete document.documentElement.dataset.theme
})

function petraIn(role: TeamRole): MeRead {
  return petra('user', [membership(settlements, role)])
}

function onPlatform(platform: string) {
  vi.spyOn(navigator, 'platform', 'get').mockReturnValue(platform)
}

const outage = alert(settlements.id)

function rule(name: string): RuleRead {
  return {
    id: `rule-${name}`,
    name,
    description: null,
    enabled: true,
    owner: { type: 'team', team_id: settlements.id },
    schema_ids: [],
    condition: { op: 'exists', field: 'payload.workflowId' },
    dedup: {},
    routing: { recipients: [{ type: 'team', team_id: settlements.id }] },
    presentation: { colour: 'red', severity: 'critical', title: name, body: '', fields: [] },
    runbook_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('opening the command menu', () => {
  test('⌘K opens it on a Mac, and the header button shows ⌘K', async () => {
    onPlatform('MacIntel')
    const { findByRole, user, queryByRole } = openAs(petraIn('member'), '/')

    const trigger = await findByRole('button', { name: 'Search' })
    expect(trigger).toHaveTextContent('⌘K')
    expect(trigger).toHaveAttribute('aria-keyshortcuts', 'Meta+K')
    expect(queryByRole('dialog')).not.toBeInTheDocument()

    await user.keyboard('{Meta>}k{/Meta}')

    const dialog = await findByRole('dialog', { name: 'Search and commands' })
    expect(within(dialog).getByRole('combobox')).toHaveFocus()
  })

  test('Ctrl K opens it elsewhere, and the header button shows Ctrl K', async () => {
    onPlatform('Win32')
    const { findByRole, user } = openAs(petraIn('member'), '/')

    const trigger = await findByRole('button', { name: 'Search' })
    expect(trigger).toHaveTextContent('Ctrl K')
    expect(trigger).toHaveAttribute('aria-keyshortcuts', 'Control+K')

    await user.keyboard('{Control>}k{/Control}')

    expect(await findByRole('dialog', { name: 'Search and commands' })).toBeInTheDocument()
  })

  test('Escape closes it and returns focus to the button that opened it', async () => {
    const { findByRole, user, queryByRole } = openAs(petraIn('member'), '/')
    const trigger = await findByRole('button', { name: 'Search' })

    await user.click(trigger)
    await findByRole('dialog', { name: 'Search and commands' })
    await user.keyboard('{Escape}')

    await waitFor(() => expect(queryByRole('dialog')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
  })

  test('Escape after the shortcut returns focus to where it was', async () => {
    const { findByRole, user, queryByRole } = openAs(petraIn('member'), '/')
    const nav = await findByRole('navigation', { name: 'Main' })
    const overview = within(nav).getByRole('link', { name: 'Overview' })
    overview.focus()

    await user.keyboard('{Control>}k{/Control}')
    await findByRole('dialog', { name: 'Search and commands' })
    await user.keyboard('{Escape}')

    await waitFor(() => expect(queryByRole('dialog')).not.toBeInTheDocument())
    expect(overview).toHaveFocus()
  })
})

describe('Navigate group', () => {
  async function navigateOptions(me: MeRead) {
    const rendered = openAs(me, '/')
    await rendered.user.click(await rendered.findByRole('button', { name: 'Search' }))
    const group = await rendered.findByRole('group', { name: 'Navigate' })
    const names = within(group)
      .getAllByRole('option')
      .map((option) => option.textContent ?? '')
    return { ...rendered, names }
  }

  test('a viewer gets the team pages and no admin pages', async () => {
    const { names } = await navigateOptions(petraIn('viewer'))

    expect(names).toEqual([
      'OverviewPages',
      'AlertsSettlements',
      'RulesSettlements',
      'RunbooksSettlements',
      'SourcesSettlements',
      'SettingsSettlements',
      'Audit logSettlements',
      'My rulesMe',
      'NotificationsMe',
      'ProfileMe',
    ])
  })

  test('an admin also gets the admin pages and opens Users', async () => {
    const { names, findByRole, user, router, queryByRole } = await navigateOptions(petra('admin', []))

    expect(names).toEqual(expect.arrayContaining(['UsersAdmin', 'TeamsAdmin', 'Audit logAdmin']))

    await user.keyboard('users')
    await user.click(await findByRole('option', { name: /^Users/ }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/admin/users'))
    expect(queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('typing filters the pages', async () => {
    const { findByRole, user } = await navigateOptions(petraIn('member'))

    await user.keyboard('notif')

    const group = await findByRole('group', { name: 'Navigate' })
    expect(within(group).getAllByRole('option').map((option) => option.textContent)).toEqual(['NotificationsMe'])
  })
})

describe('Alerts group', () => {
  test('searches the alerts the Overview already loaded, without waiting for the server', async () => {
    let calls = 0
    server.use(
      http.get(getListAlertsUrl(), async () => {
        calls += 1
        if (calls > 1) await delay('infinite')
        return HttpResponse.json([outage])
      }),
    )
    const { findByRole, findAllByText, user } = openAs(petraIn('member'), '/')
    await findAllByText(outage.title)

    await user.click(await findByRole('button', { name: 'Search' }))
    await user.keyboard('wf-8f21')

    const group = await findByRole('group', { name: 'Alerts' })
    expect(within(group).getByRole('option', { name: /Settlement wf-8f21 failed/ })).toBeInTheDocument()
  })

  test('Enter on an alert opens its detail page', async () => {
    server.use(
      respond(listAlerts, 'get', getListAlertsUrl(), 200, [outage]),
      respond(getAlert, 'get', getGetAlertUrl(outage.id), 200, outage),
      respond(getRunbookRun, 'get', getGetRunbookRunUrl(outage.id), 200, null),
      respond(listAlertDeliveries, 'get', getListAlertDeliveriesUrl(outage.id), 200, []),
      respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, []),
    )
    const { findByRole, user, router } = openAs(petraIn('viewer'), '/me/profile')

    await user.click(await findByRole('button', { name: 'Search' }))
    await user.keyboard('wf-8f21')
    await findByRole('option', { name: /Settlement wf-8f21 failed/ })
    await user.keyboard('{Enter}')

    await waitFor(() => expect(router.state.location.pathname).toBe(`/alerts/${outage.id}`))
  })

  test('a member acknowledges the highlighted alert from the menu', async () => {
    server.use(
      respond(listAlerts, 'get', getListAlertsUrl(), 200, [outage]),
      respond(acknowledgeAlert, 'post', getAcknowledgeAlertUrl(outage.id), 200, {
        ...outage,
        status: 'acknowledged',
        acknowledged_by: petraIn('member').user.id,
        acknowledged_at: '2026-11-21T12:05:00Z',
      }),
    )
    const sent = recordRequests('post', getAcknowledgeAlertUrl(outage.id))
    const { findByRole, user } = openAs(petraIn('member'), '/me/profile')

    await user.click(await findByRole('button', { name: 'Search' }))
    await user.keyboard('wf-8f21')
    await findByRole('option', { name: /Settlement wf-8f21 failed/ })
    await user.keyboard('{ArrowDown}')
    expect(await findByRole('option', { name: /^Acknowledge/, selected: true })).toBeInTheDocument()
    await user.keyboard('{Enter}')

    await waitFor(() => expect(sent).toHaveLength(1))
    expect(await findByRole('option', { name: /^Resolve/ })).toBeInTheDocument()
  })

  test('a viewer sees no Acknowledge or Resolve', async () => {
    server.use(respond(listAlerts, 'get', getListAlertsUrl(), 200, [outage]))
    const { findByRole, queryByRole, user } = openAs(petraIn('viewer'), '/me/profile')

    await user.click(await findByRole('button', { name: 'Search' }))
    await user.keyboard('wf-8f21')
    expect(await findByRole('option', { name: /Settlement wf-8f21 failed/, selected: true })).toBeInTheDocument()

    expect(queryByRole('option', { name: /^Acknowledge/ })).not.toBeInTheDocument()
    expect(queryByRole('option', { name: /^Resolve/ })).not.toBeInTheDocument()
  })
})

describe('Rules and Runbooks groups', () => {
  test("list the current team's rules and open the rule's page", async () => {
    const settlementFailed = rule('Settlement failed')
    server.use(
      respond(listRules, 'get', getListRulesUrl(), 200, [settlementFailed]),
      respond(getRule, 'get', getGetRuleUrl(settlementFailed.id), 200, settlementFailed),
    )
    withBuilderData()
    const { findByRole, user, router } = openAs(petraIn('member'), '/me/profile')

    await user.click(await findByRole('button', { name: 'Search' }))
    const group = await findByRole('group', { name: 'Rules in Settlements' })
    await user.click(await within(group).findByRole('option', { name: 'Settlement failed' }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/teams/settlements/rules/${settlementFailed.id}`),
    )
  })

  test('a 501 stub shows one quiet line in its group', async () => {
    server.use(
      http.get(getListRulesUrl(), () => HttpResponse.json({ detail: 'Not implemented' }, { status: 501 })),
      http.get(getListRunbooksUrl(), () => HttpResponse.json({ detail: 'Not implemented' }, { status: 501 })),
    )
    const { findByRole, user } = openAs(petraIn('member'), '/me/profile')

    await user.click(await findByRole('button', { name: 'Search' }))

    const rules = await findByRole('group', { name: 'Rules in Settlements' })
    expect(await within(rules).findByText("This feature isn't available yet.")).toBeInTheDocument()
    const runbooks = await findByRole('group', { name: 'Runbooks in Settlements' })
    expect(await within(runbooks).findByText("This feature isn't available yet.")).toBeInTheDocument()
  })
})

describe('Actions group', () => {
  test('switching the theme updates the page and the header toggle', async () => {
    const { findByRole, getByRole, user } = openAs(petraIn('member'), '/me/profile')

    await user.click(await findByRole('button', { name: 'Search' }))
    await user.click(await findByRole('option', { name: 'Switch to dark theme' }))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('theme')).toBe('dark')
    const toggle = getByRole('group', { name: 'Theme', hidden: true })
    expect(within(toggle).getByRole('button', { name: 'Dark', hidden: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })
})
