import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { act, waitFor, within } from '@testing-library/react'
import {
  acknowledgeAlert,
  decideStep,
  getAcknowledgeAlertUrl,
  getAlert,
  getDecideStepUrl,
  getGetAlertUrl,
  getGetRunbookRunUrl,
  getListAlertDeliveriesUrl,
  getListAlertsQueryKey,
  getRunbookRun,
  listAlertDeliveries,
} from '@/api/generated/alerts/alerts'
import { getListAuditEntriesUrl, listAuditEntries } from '@/api/generated/audit/audit'
import type {
  AlertRead,
  AuditEntryRead,
  DeliveryRead,
  MeRead,
  RunbookRunRead,
  StepRunRead,
  TeamRole,
} from '@/api/generated/model'
import { getListTeamMembersQueryKey } from '@/api/generated/teams/teams'
import { AlertCard } from '@/components/alerts/alert-card'
import { Toaster } from '@/components/ui/sonner'
import { alert, auditEntry, delivery, runbookRun, stepRun } from '@/test/alerts'
import { respond } from '@/test/http'
import { membership, petra, team } from '@/test/people'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { member, recordRequests, user } from '@/test/teams'
import { AlertDetail } from './alert-detail'

const settlements = team('settlements', 'Settlements')
const support = team('support', 'Counterparty support')
const bob = user('bob', 'Bob Novak')

function asRole(role: TeamRole): MeRead {
  return petra('user', [membership(settlements, role), membership(support, 'viewer')])
}

const fired = alert(settlements.id, {
  payload: { workflowId: 'wf-8f21', phone: '+420 601 000 111' },
  occurrences: 3,
  escalated_team_ids: [support.id],
})

/** One step in every status, in the brief's settlement runbook order (SPEC §11.4) plus the other actions. */
function everyStatus(): StepRunRead[] {
  return [
    stepRun(
      0,
      { action: 'http_get', url: 'http://counterparty-service/health', check: 'Is counterparty-service healthy?' },
      { status: 'succeeded', attempts: 1, result: 'HTTP 200 in 35 ms' },
    ),
    stepRun(1, { action: 'retry_workflow', workflowId: '{{workflowId}}', approval: 'none' }, {
      status: 'failed',
      attempts: 2,
      failures: 2,
      result: 'Workflow failed again',
    }),
    stepRun(
      2,
      { action: 'escalate', team: 'counterparty-support', approval: 'required', if: { step: 1, failures_gte: 2 } },
      { status: 'awaiting_approval' },
    ),
    stepRun(3, { action: 'manual', text: 'Call the counterparty on {{payload.phone}}' }, { status: 'awaiting_manual' }),
    stepRun(4, { action: 'restart_service', service: 'settlement-{{workflowId}}', if: 'the queue is still growing' }, {
      status: 'awaiting_answer',
    }),
    stepRun(5, { action: 'call_webhook', url: 'https://hooks.example.com/{{payload.workflowId}}' }, {
      status: 'running',
    }),
    stepRun(6, { action: 'wait', seconds: 90 }, { status: 'pending' }),
    stepRun(7, { action: 'open_ticket', title: 'Settlement {{workflowId}} stuck' }, {
      status: 'skipped',
      decided_by: bob.id,
      decided_at: '2026-11-21T12:04:00Z',
    }),
  ]
}

interface Endpoints {
  alert?: AlertRead
  run?: RunbookRunRead | null
  deliveries?: DeliveryRead[]
  audit?: AuditEntryRead[]
}

/** Answers the four requests the detail sends on load; each test overrides the one it is about with `server.use`. */
function detailEndpoints({ alert: shown = fired, run = null, deliveries = [], audit = [] }: Endpoints = {}) {
  server.use(
    respond(getAlert, 'get', getGetAlertUrl(shown.id), 200, shown),
    respond(getRunbookRun, 'get', getGetRunbookRunUrl(shown.id), 200, run),
    respond(listAlertDeliveries, 'get', getListAlertDeliveriesUrl(shown.id), 200, deliveries),
    respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, audit),
  )
}

/** Puts Bob in the cached `GET /teams/{id}/members` of Settlements, as if the members page had loaded it. */
function SeedMembers() {
  const queryClient = useQueryClient()
  useState(() =>
    queryClient.setQueryData(getListTeamMembersQueryKey(settlements.id), {
      status: 200,
      data: [member(bob, 'member')],
      headers: new Headers(),
    }),
  )
  return null
}

function renderDetail(me: MeRead = asRole('member'), shown: AlertRead = fired) {
  return renderWithProviders(
    <>
      <SeedMembers />
      <AlertDetail alertId={shown.id} />
      <Toaster />
    </>,
    { me, route: `/alerts/${shown.id}` },
  )
}

function stepItem(container: HTMLElement, number: number): HTMLElement {
  const item = within(container).getAllByRole('listitem').find((element) =>
    element.getAttribute('aria-label')?.startsWith(`Step ${number}:`),
  )
  if (item === undefined) throw new Error(`No step ${number}`)
  return item
}

describe('GET /alerts/{id}', () => {
  test('shows the alert: severity, status, title, body, fields, counter, team, escalations and times', async () => {
    detailEndpoints()
    const { findByRole, getByText, getByLabelText } = renderDetail()

    expect(await findByRole('heading', { level: 1, name: fired.title })).toBeInTheDocument()
    expect(getByText('Critical')).toBeInTheDocument()
    expect(getByText('Open')).toBeInTheDocument()
    expect(getByText(fired.body ?? '')).toBeInTheDocument()
    expect(getByText('payload.amount')).toBeInTheDocument()
    expect(getByText('12,400,000')).toBeInTheDocument()
    expect(getByLabelText('3 occurrences')).toBeInTheDocument()
    expect(getByText('Settlements')).toBeInTheDocument()
    expect(getByText('Counterparty support')).toBeInTheDocument()
    expect(getByText('First seen')).toBeInTheDocument()
    expect(getByText('Last seen')).toBeInTheDocument()
  })

  test('shows a skeleton while the alert loads', async () => {
    server.use(http.get(getGetAlertUrl(fired.id), async () => delay('infinite')))
    const { findByRole } = renderDetail()
    expect(await findByRole('status', { name: 'Loading alert' })).toBeInTheDocument()
  })

  test.each([404, 422] as const)('%i shows the 404 page inside the shell', async (status) => {
    server.use(
      status === 404
        ? respond(getAlert, 'get', getGetAlertUrl(fired.id), 404, { detail: 'Alert not found' })
        : respond(getAlert, 'get', getGetAlertUrl(fired.id), 422, {
            detail: [{ loc: ['path', 'alert_id'], msg: 'Input should be a valid UUID', type: 'uuid_parsing' }],
          }),
    )
    const { findByRole } = renderDetail()
    expect(await findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })

  test('a 501 shows the shared fallback with Try again', async () => {
    server.use(http.get(getGetAlertUrl(fired.id), () => new HttpResponse(null, { status: 501 })))
    const { findByText, getByRole } = renderDetail()
    expect(await findByText("This feature isn't available yet.")).toBeInTheDocument()
    expect(getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  test('a network failure says to check the connection', async () => {
    server.use(http.get(getGetAlertUrl(fired.id), () => HttpResponse.error()))
    const { findByText } = renderDetail()
    expect(await findByText("Couldn't load the alert")).toBeInTheDocument()
  })

  test('follows the alert in a cached live feed without opening a stream', async () => {
    detailEndpoints()
    const { findByRole, findByText, findByLabelText, queryClient } = renderDetail()
    await findByRole('heading', { level: 1, name: fired.title })

    act(() => {
      queryClient.setQueryData(getListAlertsQueryKey({ team_id: settlements.id }), {
        status: 200,
        data: [{ ...fired, status: 'acknowledged', acknowledged_by: bob.id, occurrences: 5 }],
        headers: new Headers(),
      })
    })

    expect(await findByText('Someone is on it')).toBeInTheDocument()
    expect(await findByLabelText('5 occurrences')).toBeInTheDocument()
  })

  test('a member acknowledges from the detail; viewers get no buttons', async () => {
    detailEndpoints()
    server.use(
      respond(acknowledgeAlert, 'post', getAcknowledgeAlertUrl(fired.id), 200, {
        ...fired,
        status: 'acknowledged',
        acknowledged_by: asRole('member').user.id,
      }),
    )
    const { findByRole, findByText, user: clicker } = renderDetail()

    await clicker.click(await findByRole('button', { name: 'Acknowledge' }))

    expect(await findByText("You're on it")).toBeInTheDocument()
    expect(await findByText('Alert acknowledged')).toBeInTheDocument()
    expect(await findByRole('button', { name: 'Resolve' })).toBeInTheDocument()
  })

  test('a viewer sees the alert without Acknowledge', async () => {
    detailEndpoints()
    const { findByRole, queryByRole } = renderDetail(asRole('viewer'))
    await findByRole('heading', { level: 1, name: fired.title })
    expect(queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
  })

  test('an alert card title links to the detail', async () => {
    const { findByRole } = renderWithProviders(<AlertCard alert={fired} />, { me: asRole('member') })
    expect(await findByRole('link', { name: fired.title })).toHaveAttribute('href', `/alerts/${fired.id}`)
  })
})

describe('GET /alerts/{id}/runbook-run', () => {
  test('an alert without a runbook says so', async () => {
    detailEndpoints({ run: null })
    const { findByText } = renderDetail()
    expect(await findByText('No runbook for this alert')).toBeInTheDocument()
  })

  test('lists the steps in order with action, filled-in parameters, status, attempts, result and decider', async () => {
    const steps = everyStatus()
    detailEndpoints({ run: runbookRun(fired.id, steps.toReversed()) })
    const { findByRole } = renderDetail()

    const list = await findByRole('list', { name: 'Runbook steps' })
    const labels = within(list)
      .getAllByRole('listitem')
      .map((item) => item.getAttribute('aria-label'))
    expect(labels).toEqual([
      'Step 1: Check a URL',
      'Step 2: Retry the workflow',
      'Step 3: Escalate to another team',
      'Step 4: Do it by hand',
      'Step 5: Restart a service',
      'Step 6: Call a webhook',
      'Step 7: Wait',
      'Step 8: Open a ticket',
    ])

    const check = stepItem(list, 1)
    expect(within(check).getByText('Succeeded')).toBeInTheDocument()
    expect(within(check).getByText('Is counterparty-service healthy?')).toBeInTheDocument()
    expect(within(check).getByText('http://counterparty-service/health')).toBeInTheDocument()
    expect(within(check).getByText('HTTP 200 in 35 ms')).toBeInTheDocument()
    expect(within(check).getByText('1 attempt')).toBeInTheDocument()

    const retry = stepItem(list, 2)
    expect(within(retry).getByText('Failed')).toBeInTheDocument()
    expect(within(retry).getByText('wf-8f21')).toBeInTheDocument()
    expect(within(retry).getByText('2 failures')).toBeInTheDocument()
    expect(within(retry).getByText('Workflow failed again')).toBeInTheDocument()

    const escalate = stepItem(list, 3)
    expect(within(escalate).getByText('Needs approval')).toBeInTheDocument()
    expect(within(escalate).getByText('Runs when step 2 (Retry the workflow) has failed twice or more.')).toBeInTheDocument()
    expect(within(escalate).getByText('counterparty-support')).toBeInTheDocument()

    expect(within(stepItem(list, 4)).getByText('Call the counterparty on +420 601 000 111')).toBeInTheDocument()
    expect(within(stepItem(list, 4)).getByText('To do by hand')).toBeInTheDocument()
    expect(within(stepItem(list, 5)).getByText('the queue is still growing?')).toBeInTheDocument()
    expect(within(stepItem(list, 5)).getByText('settlement-wf-8f21')).toBeInTheDocument()
    expect(within(stepItem(list, 6)).getByText('Running')).toBeInTheDocument()
    expect(within(stepItem(list, 6)).getByText('https://hooks.example.com/wf-8f21')).toBeInTheDocument()
    expect(within(stepItem(list, 6)).getByText('POST')).toBeInTheDocument()
    expect(within(stepItem(list, 7)).getByText('Waiting')).toBeInTheDocument()
    expect(within(stepItem(list, 7)).getByText('1 minute 30 seconds')).toBeInTheDocument()

    const ticket = stepItem(list, 8)
    expect(within(ticket).getByText('Skipped')).toBeInTheDocument()
    expect(within(ticket).getByRole('heading', { name: 'Open a ticket' })).toHaveClass('line-through')
    expect(within(ticket).getByText('Bob Novak')).toBeInTheDocument()
  })

  test('shows a skeleton while the run loads', async () => {
    detailEndpoints()
    server.use(http.get(getGetRunbookRunUrl(fired.id), async () => delay('infinite')))
    const { findByRole } = renderDetail()
    expect(await findByRole('status', { name: 'Loading runbook steps' })).toBeInTheDocument()
  })

  test('404 says the alert is gone; 501 shows the shared fallback', async () => {
    detailEndpoints()
    server.use(respond(getRunbookRun, 'get', getGetRunbookRunUrl(fired.id), 404, { detail: 'Alert not found' }))
    const { findByText, unmount } = renderDetail()
    expect(await findByText("This alert no longer exists, or you can't see it any more.")).toBeInTheDocument()
    unmount()

    server.use(http.get(getGetRunbookRunUrl(fired.id), () => new HttpResponse(null, { status: 501 })))
    const second = renderDetail()
    expect(await second.findByText("This feature isn't available yet.")).toBeInTheDocument()
  })
})

describe('POST /alerts/{id}/runbook-run/steps/{index}/decision', () => {
  /** The run after step `index` moved to `status`. */
  function after(index: number, status: StepRunRead['status']): RunbookRunRead {
    return runbookRun(
      fired.id,
      everyStatus().map((step) =>
        step.index === index
          ? { ...step, status, decided_by: asRole('lead').user.id, decided_at: '2026-11-21T12:06:00Z' }
          : step,
      ),
    )
  }

  test.each([
    ['viewer', [], ['Waiting for a team lead to approve.', 'Waiting for a team member.']],
    ['member', ['Mark as done', 'Yes', 'No'], ['Waiting for a team lead to approve.']],
    ['lead', ['Approve step', 'Reject step', 'Mark as done', 'Yes', 'No'], []],
  ] as const)('a %s sees only the decisions their role allows', async (role, buttons, waiting) => {
    detailEndpoints({ run: runbookRun(fired.id, everyStatus()) })
    const { findByRole, queryAllByRole, queryAllByText } = renderDetail(asRole(role))
    await findByRole('list', { name: 'Runbook steps' })

    const decisionButtons = queryAllByRole('button')
      .map((button) => button.textContent)
      .filter((text) => ['Approve step', 'Reject step', 'Yes', 'No', 'Mark as done'].includes(text ?? ''))
    expect(decisionButtons).toEqual(buttons)
    for (const line of waiting) expect(queryAllByText(line).length).toBeGreaterThan(0)
    if (role === 'lead') expect(queryAllByText(/^Waiting for a team/)).toHaveLength(0)
  })

  test('a lead approves after a dialog that names what will run; the step runs at once', async () => {
    detailEndpoints({ run: runbookRun(fired.id, everyStatus()) })
    const sent = recordRequests('post', getDecideStepUrl(fired.id, 2))
    server.use(
      http.post(getDecideStepUrl(fired.id, 2), async () => {
        await delay(50)
        return HttpResponse.json(after(2, 'running'))
      }),
    )
    const { findByRole, findByText, user: clicker } = renderDetail(asRole('lead'))
    const list = await findByRole('list', { name: 'Runbook steps' })

    await clicker.click(within(stepItem(list, 3)).getByRole('button', { name: 'Approve step' }))
    const dialog = await findByRole('alertdialog', { name: 'Approve step 3: Escalate to another team?' })
    expect(
      within(dialog).getByText(
        'Escalates the alert to team counterparty-support, whose people get notified. It runs as soon as you approve.',
      ),
    ).toBeInTheDocument()
    await clicker.click(within(dialog).getByRole('button', { name: 'Approve step' }))

    expect(await within(stepItem(list, 3)).findByText('Running')).toBeInTheDocument()
    expect(await findByText('Step approved')).toBeInTheDocument()
    await waitFor(() => expect(sent[0]?.body).toEqual({ decision: 'approve' }))
    await waitFor(() => expect(dialog).not.toBeInTheDocument())
  })

  test.each([
    ['Reject step', 3, 2, 'reject', 'skipped', 'Skipped', 'Step rejected'],
    ['Yes', 5, 4, 'yes', 'running', 'Running', 'Answered yes'],
    ['No', 5, 4, 'no', 'skipped', 'Skipped', 'Answered no'],
    ['Mark as done', 4, 3, 'done', 'succeeded', 'Succeeded', 'Step marked as done'],
  ] as const)('%s sends %s and shows the new status', async (button, number, index, decision, status, words, toast) => {
    detailEndpoints({ run: runbookRun(fired.id, everyStatus()) })
    const sent = recordRequests('post', getDecideStepUrl(fired.id, index))
    server.use(respond(decideStep, 'post', getDecideStepUrl(fired.id, index), 200, after(index, status)))
    const { findByRole, findByText, user: clicker } = renderDetail(asRole('lead'))
    const list = await findByRole('list', { name: 'Runbook steps' })

    await clicker.click(within(stepItem(list, number)).getByRole('button', { name: button }))

    expect(await within(stepItem(list, number)).findByText(words)).toBeInTheDocument()
    expect(await findByText(toast)).toBeInTheDocument()
    await waitFor(() => expect(sent[0]?.body).toEqual({ decision }))
  })

  test('409 puts the step back, says why, and reloads the run', async () => {
    let loads = 0
    detailEndpoints()
    server.use(
      http.get(getGetRunbookRunUrl(fired.id), () => {
        loads += 1
        return HttpResponse.json(runbookRun(fired.id, everyStatus()))
      }),
      respond(decideStep, 'post', getDecideStepUrl(fired.id, 3), 409, { detail: 'Step is not awaiting a manual tick' }),
    )
    const { findByRole, user: clicker } = renderDetail(asRole('member'))
    const list = await findByRole('list', { name: 'Runbook steps' })

    await clicker.click(within(stepItem(list, 4)).getByRole('button', { name: 'Mark as done' }))

    expect(
      await within(stepItem(list, 4)).findByText(
        'Someone else decided this step first, or it moved on. The list now shows its current state.',
      ),
    ).toBeInTheDocument()
    expect(within(stepItem(list, 4)).getByText('To do by hand')).toBeInTheDocument()
    await waitFor(() => expect(loads).toBe(2))
  })

  test.each([
    [403, 'Only a team lead can reject this step.'],
    [404, "This alert no longer exists, or you can't see it any more."],
    [400, "Couldn't save the decision. Reload the page and try again."],
  ] as const)('%i shows its message under the step', async (status, message) => {
    detailEndpoints({ run: runbookRun(fired.id, everyStatus()) })
    server.use(respond(decideStep, 'post', getDecideStepUrl(fired.id, 2), status, { detail: 'refused' }))
    const { findByRole, user: clicker } = renderDetail(asRole('lead'))
    const list = await findByRole('list', { name: 'Runbook steps' })

    await clicker.click(within(stepItem(list, 3)).getByRole('button', { name: 'Reject step' }))

    expect(await within(stepItem(list, 3)).findByText(message)).toBeInTheDocument()
    expect(within(stepItem(list, 3)).getByText('Needs approval')).toBeInTheDocument()
  })

  test('a refused approval stays in the dialog', async () => {
    detailEndpoints({ run: runbookRun(fired.id, everyStatus()) })
    server.use(respond(decideStep, 'post', getDecideStepUrl(fired.id, 2), 403, { detail: 'Leads only' }))
    const { findByRole, user: clicker } = renderDetail(asRole('lead'))
    const list = await findByRole('list', { name: 'Runbook steps' })

    await clicker.click(within(stepItem(list, 3)).getByRole('button', { name: 'Approve step' }))
    const dialog = await findByRole('alertdialog')
    await clicker.click(within(dialog).getByRole('button', { name: 'Approve step' }))

    expect(await within(dialog).findByText('Only a team lead can approve this step.')).toBeInTheDocument()
  })

  test('422 and a 501 stub each show a message', async () => {
    detailEndpoints({ run: runbookRun(fired.id, everyStatus()) })
    server.use(
      respond(decideStep, 'post', getDecideStepUrl(fired.id, 4), 422, {
        detail: [{ loc: ['body', 'decision'], msg: 'Input should be a valid enum member', type: 'enum' }],
      }),
      http.post(getDecideStepUrl(fired.id, 3), () => new HttpResponse(null, { status: 501 })),
    )
    const { findByRole, user: clicker } = renderDetail(asRole('member'))
    const list = await findByRole('list', { name: 'Runbook steps' })

    await clicker.click(within(stepItem(list, 5)).getByRole('button', { name: 'No' }))
    expect(
      await within(stepItem(list, 5)).findByText("Couldn't save the decision. Reload the page and try again."),
    ).toBeInTheDocument()

    await clicker.click(within(stepItem(list, 4)).getByRole('button', { name: 'Mark as done' }))
    expect(await within(stepItem(list, 4)).findByText("This feature isn't available yet.")).toBeInTheDocument()
  })
})

describe('GET /alerts/{id}/deliveries', () => {
  test('one row per recipient and channel, with status, attempts, last error and the message behind a button', async () => {
    const me = asRole('member')
    const unknownId = '0193c000-aaaa-7000-8000-000000000001'
    detailEndpoints({
      deliveries: [
        delivery(fired.id, me.user.id),
        delivery(fired.id, bob.id, { channel: 'email', status: 'pending', sent_at: null, message: 'Full email body' }),
        delivery(fired.id, unknownId, {
          channel: 'phone',
          status: 'failed',
          attempts: 3,
          sent_at: null,
          last_error: 'Gateway timeout',
        }),
      ],
    })
    const { findByRole, getByText, user: clicker } = renderDetail(me)

    const table = await findByRole('table', { name: 'Deliveries' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(3)
    expect(within(rows[0]).getByText('You')).toBeInTheDocument()
    expect(within(rows[0]).getByText(/Sent by SMS/)).toBeInTheDocument()
    expect(within(rows[1]).getByText('Bob Novak')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Sending by email')).toBeInTheDocument()
    expect(within(rows[2]).getByText('User 0193c000')).toHaveAttribute('title', unknownId)
    expect(within(rows[2]).getByText('Phone call failed, retrying. 3 attempts so far')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Gateway timeout')).toBeInTheDocument()

    await clicker.click(within(rows[1]).getByRole('button', { name: 'Show message' }))
    expect(getByText('Full email body')).toBeInTheDocument()
    await clicker.click(within(rows[1]).getByRole('button', { name: 'Hide message' }))
    expect(within(table).queryByText('Full email body')).not.toBeInTheDocument()
  })

  test('no deliveries says nobody was notified', async () => {
    detailEndpoints({ deliveries: [] })
    const { findByText } = renderDetail()
    expect(await findByText('Nobody was notified')).toBeInTheDocument()
  })

  test('shows a skeleton while deliveries load', async () => {
    detailEndpoints()
    server.use(http.get(getListAlertDeliveriesUrl(fired.id), async () => delay('infinite')))
    const { findByRole } = renderDetail()
    expect(await findByRole('status', { name: 'Loading deliveries' })).toBeInTheDocument()
  })

  test('404 says the alert is gone; 501 shows the shared fallback', async () => {
    detailEndpoints()
    server.use(
      respond(listAlertDeliveries, 'get', getListAlertDeliveriesUrl(fired.id), 404, { detail: 'Alert not found' }),
    )
    const { findByText, unmount } = renderDetail()
    expect(await findByText("This alert no longer exists, or you can't see it any more.")).toBeInTheDocument()
    unmount()

    server.use(http.get(getListAlertDeliveriesUrl(fired.id), () => new HttpResponse(null, { status: 501 })))
    const second = renderDetail()
    expect(await second.findByText("This feature isn't available yet.")).toBeInTheDocument()
  })
})

describe('GET /audit', () => {
  test('asks for this alert and shows a timeline: actor or System, the action in words, the time', async () => {
    const me = asRole('member')
    const queries: URLSearchParams[] = []
    detailEndpoints()
    server.use(
      http.get(getListAuditEntriesUrl(), ({ request }) => {
        queries.push(new URL(request.url).searchParams)
        return HttpResponse.json([
          auditEntry(fired.id, me.user.id, 'alert.acknowledged'),
          auditEntry(fired.id, null, 'step.succeeded'),
          auditEntry(fired.id, null, 'alert.renotified'),
        ])
      }),
    )
    const { findByRole } = renderDetail(me)

    const history = await findByRole('list', { name: 'History' })
    const items = within(history).getAllByRole('listitem')
    expect(items.map((item) => item.querySelector('p')?.textContent)).toEqual([
      'You: Acknowledged the alert',
      'System: A step succeeded',
      'System: Alert renotified',
    ])
    expect(within(items[0]).getByRole('time')).toHaveAttribute('dateTime', '2026-11-21T12:05:00Z')
    expect(queries[0]?.get('entity_type')).toBe('alert')
    expect(queries[0]?.get('entity_id')).toBe(fired.id)
  })

  test('no entries says so', async () => {
    detailEndpoints({ audit: [] })
    const { findByText } = renderDetail()
    expect(await findByText('No history yet')).toBeInTheDocument()
  })

  test('422 and a 501 stub each show a message', async () => {
    detailEndpoints()
    server.use(
      respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 422, {
        detail: [{ loc: ['query', 'entity_id'], msg: 'Invalid', type: 'value_error' }],
      }),
    )
    const { findByText, unmount } = renderDetail()
    expect(await findByText("Couldn't load the history. Reload the page and try again.")).toBeInTheDocument()
    unmount()

    server.use(http.get(getListAuditEntriesUrl(), () => new HttpResponse(null, { status: 501 })))
    const second = renderDetail()
    expect(await second.findByText("This feature isn't available yet.")).toBeInTheDocument()
  })
})
