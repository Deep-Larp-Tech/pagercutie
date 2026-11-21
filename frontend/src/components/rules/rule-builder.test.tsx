import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import type { RuleCreate } from '@/api/generated/model'
import {
  createRule,
  deleteRule,
  getCreateRuleUrl,
  getDeleteRuleUrl,
  getGetRuleUrl,
  getListRulesUrl,
  getRule,
  getTestRuleUrl,
  getUpdateRuleUrl,
  listRules,
  testRule,
  updateRule,
} from '@/api/generated/rules/rules'
import { respond } from '@/test/http'
import { membership, petra, team } from '@/test/people'
import { settlementsRule, settlementTimeout, tradeSchema, withBuilderData, workflowSchema } from '@/test/rules'
import { server } from '@/test/server'
import { openAs, petraIn, recordRequests, settlements } from '@/test/teams'

vi.setConfig({ testTimeout: 30_000 })

afterEach(() => {
  toast.dismiss()
})

const rule = settlementsRule()
const NEW_PATH = '/teams/settlements/rules/new'
const EDIT_PATH = `/teams/settlements/rules/${rule.id}`
const createUrl = getCreateRuleUrl()
const ruleUrl = getGetRuleUrl(rule.id)

async function pick(user: UserEvent, combobox: string, option: string) {
  await user.click(await screen.findByRole('combobox', { name: combobox }))
  await user.click(await screen.findByRole('option', { name: option }))
}

async function typeInto(user: UserEvent, label: string, text: string) {
  const input = await screen.findByLabelText(label, {}, { timeout: 5000 })
  await user.clear(input)
  await user.type(input, text)
  await user.keyboard('{Escape}')
}

async function paste(user: UserEvent, label: string, text: string) {
  await user.click(screen.getByLabelText(label))
  await user.paste(text)
}

async function addPath(user: UserEvent, list: string, path: string) {
  await user.type(screen.getByRole('combobox', { name: `Add to ${list}` }), path)
  await user.keyboard('{Escape}')
  await user.click(within(screen.getByRole('combobox', { name: `Add to ${list}` }).closest('div.flex') ?? document.body).getByRole('button', { name: 'Add' }))
}

function openEdit(role: Parameters<typeof petraIn>[0] = 'member') {
  withBuilderData()
  server.use(respond(getRule, 'get', ruleUrl, 200, rule))
  return openAs(petraIn(role), EDIT_PATH)
}

describe('POST /rules', () => {
  test("Team Settlements' rule built through the UI sends the SPEC §4.3 body", async () => {
    withBuilderData()
    server.use(respond(createRule, 'post', createUrl, 201, rule), respond(listRules, 'get', getListRulesUrl(), 200, [rule]))
    const posts = recordRequests('post', createUrl)
    const { user, findAllByText } = openAs(petraIn('member'), NEW_PATH)

    await typeInto(user, 'Rule name', 'Order settlement failed in prod')
    await pick(user, 'Event schemas', 'workflow v1')
    await typeInto(user, 'Field 1', 'payload.type')
    await typeInto(user, 'Value 1', 'WORKFLOW_FAILED')
    await user.click(screen.getByRole('button', { name: 'Add condition' }))
    await typeInto(user, 'Field 2', 'payload.workflowName')
    await typeInto(user, 'Value 2', 'order-settlement')
    await user.click(screen.getByRole('button', { name: 'Add condition' }))
    await typeInto(user, 'Field 3', 'payload.environment')
    await typeInto(user, 'Value 3', 'prod')
    expect(screen.getByTestId('condition-sentence')).toHaveTextContent(
      'type is WORKFLOW_FAILED and workflowName is order-settlement and environment is prod',
    )

    expect(screen.getByRole('list', { name: 'Recipients' })).toHaveTextContent('On call in Settlements')
    await user.click(screen.getByRole('switch', { name: "Use each person's notification settings" }))
    await user.click(screen.getByRole('button', { name: 'Phone call' }))
    await user.click(screen.getByRole('button', { name: 'SMS' }))

    await paste(user, 'Title', 'Settlement {{payload.workflowId}} failed at {{payload.step}}')
    await paste(user, 'Body (optional)', '{{payload.error.message}}')
    await addPath(user, 'fields on the alert', 'payload.step')
    await addPath(user, 'fields on the alert', 'payload.error.message')
    await addPath(user, 'fields that identify a problem', 'payload.workflowId')
    await pick(user, 'Runbook', 'Settlement timeout')

    await user.click(screen.getByRole('button', { name: 'Save rule' }))

    expect((await findAllByText('Rule saved')).length).toBeGreaterThan(0)
    const expected: RuleCreate = {
      name: 'Order settlement failed in prod',
      description: null,
      enabled: true,
      owner: { type: 'team', team_id: settlements.id },
      schema_ids: [workflowSchema.id],
      condition: rule.condition,
      dedup: { fields: ['payload.workflowId'], window_s: 300 },
      routing: { recipients: [{ type: 'on_call', team_id: settlements.id }], channels: ['sms', 'phone'] },
      presentation: rule.presentation,
      runbook_id: settlementTimeout.id,
    }
    await waitFor(() => expect(posts.map(({ body }) => body)).toEqual([expected]))
    expect(await screen.findByRole('heading', { name: 'Rules' })).toBeInTheDocument()
  })

  test("Team Rates' rule: glob, a number with grouping, everyone in the team by email and in the app", async () => {
    const rates = team('rates', 'Rates')
    withBuilderData(rates.id)
    server.use(respond(createRule, 'post', createUrl, 201, rule), respond(listRules, 'get', getListRulesUrl(), 200, []))
    const posts = recordRequests('post', createUrl)
    const { user, findAllByText } = openAs(petra('user', [membership(rates, 'member')]), '/teams/rates/rules/new')

    await typeInto(user, 'Rule name', 'Large rates trade rejected')
    await pick(user, 'Event schemas', 'trade v1')
    await typeInto(user, 'Field 1', 'payload.type')
    await pick(user, 'Operator 1', 'matches the pattern')
    await typeInto(user, 'Value 1', 'trade.rejected.*')
    await user.click(screen.getByRole('button', { name: 'Add condition' }))
    await typeInto(user, 'Field 2', 'payload.desk')
    await typeInto(user, 'Value 2', 'rates')
    await user.click(screen.getByRole('button', { name: 'Add condition' }))
    await typeInto(user, 'Field 3', 'payload.notional')
    await pick(user, 'Operator 3', 'is more than')
    await typeInto(user, 'Value 3', '10,000,000')
    expect(screen.getByTestId('condition-sentence')).toHaveTextContent(
      'type matches the pattern trade.rejected.* and desk is rates and notional is more than 10,000,000',
    )

    await pick(user, 'Notify', 'Everyone in a team')
    await user.click(screen.getByRole('button', { name: 'Add recipient' }))
    await user.click(screen.getByRole('button', { name: 'Remove On call in Rates' }))
    expect(screen.getByRole('list', { name: 'Recipients' })).toHaveTextContent('Everyone in Rates')
    await user.click(screen.getByRole('switch', { name: "Use each person's notification settings" }))
    await user.click(screen.getByRole('button', { name: 'Email' }))
    await user.click(screen.getByRole('button', { name: 'In the app' }))

    await paste(user, 'Title', 'Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}')
    await pick(user, 'Severity', 'Error')
    expect(screen.getByRole('combobox', { name: 'Colour' })).toHaveTextContent('Orange')

    await user.click(screen.getByRole('button', { name: 'Save rule' }))

    expect((await findAllByText('Rule saved')).length).toBeGreaterThan(0)
    const expected: RuleCreate = {
      name: 'Large rates trade rejected',
      description: null,
      enabled: true,
      owner: { type: 'team', team_id: rates.id },
      schema_ids: [tradeSchema.id],
      condition: {
        op: 'and',
        args: [
          { op: 'glob', field: 'payload.type', value: 'trade.rejected.*' },
          { op: 'eq', field: 'payload.desk', value: 'rates' },
          { op: 'gt', field: 'payload.notional', value: 10000000 },
        ],
      },
      dedup: { fields: [], window_s: 300 },
      routing: { recipients: [{ type: 'team', team_id: rates.id }], channels: ['email', 'ui'] },
      presentation: {
        title: 'Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}',
        body: null,
        fields: [],
        severity: 'error',
        colour: 'orange',
      },
      runbook_id: null,
    }
    await waitFor(() => expect(posts.map(({ body }) => body)).toEqual([expected]))
  })

  test("Anna's personal rule notifies only her and uses her channel preferences", async () => {
    const anna = petra('user', [membership(settlements, 'member')])
    withBuilderData(null)
    server.use(respond(createRule, 'post', createUrl, 201, rule), respond(listRules, 'get', getListRulesUrl(), 200, []))
    const posts = recordRequests('post', createUrl)
    const { user, findAllByText, queryByRole, getByText } = openAs(anna, '/me/rules/new')

    await typeInto(user, 'Rule name', 'Payments API critical')
    expect(getByText('This rule notifies only you.')).toBeInTheDocument()
    expect(queryByRole('combobox', { name: 'Runbook' })).not.toBeInTheDocument()
    await typeInto(user, 'Field 1', 'source')
    await typeInto(user, 'Value 1', 'payments-api')
    await user.click(screen.getByRole('button', { name: 'Add condition' }))
    await typeInto(user, 'Field 2', 'severity')
    await pick(user, 'Value 2', 'Critical')
    expect(screen.getByTestId('condition-sentence')).toHaveTextContent('source is payments-api and severity is Critical')
    await paste(user, 'Title', 'Payments API: {{payload.message}}')

    await user.click(screen.getByRole('button', { name: 'Save rule' }))

    expect((await findAllByText('Rule saved')).length).toBeGreaterThan(0)
    await waitFor(() =>
      expect(posts[0]?.body).toMatchObject({
        owner: { type: 'user', user_id: anna.user.id },
        condition: {
          op: 'and',
          args: [
            { op: 'eq', field: 'source', value: 'payments-api' },
            { op: 'eq', field: 'severity', value: 'critical' },
          ],
        },
        routing: { recipients: [{ type: 'user', user_id: anna.user.id }], channels: null },
        runbook_id: null,
      }),
    )
  })

  test('the client check keeps an unfinished rule from being sent', async () => {
    withBuilderData()
    const posts = recordRequests('post', createUrl)
    const { user, findByText, getByRole } = openAs(petraIn('member'), NEW_PATH)

    await user.click(await screen.findByRole('button', { name: 'Save rule' }))

    expect(await findByText("Couldn't save the rule. Fix the highlighted fields and try again.")).toBeInTheDocument()
    expect(screen.getByText('Give the rule a name.')).toBeInTheDocument()
    expect(within(getByRole('group', { name: 'Condition 1' })).getByText('Pick or type a field.')).toBeInTheDocument()
    expect(posts).toEqual([])
  })

  test('picking a severity pre-fills the colour until one is picked by hand', async () => {
    withBuilderData()
    const { user } = openAs(petraIn('member'), NEW_PATH)

    await pick(user, 'Severity', 'Warning')
    expect(screen.getByRole('combobox', { name: 'Colour' })).toHaveTextContent('Yellow')
    await pick(user, 'Colour', 'Green')
    await pick(user, 'Severity', 'Info')

    expect(screen.getByRole('combobox', { name: 'Colour' })).toHaveTextContent('Green')
    expect(screen.getByText('Picked by hand.')).toBeInTheDocument()
  })

  async function fillMinimal(user: UserEvent) {
    await typeInto(user, 'Rule name', 'Anything')
    await typeInto(user, 'Field 1', 'payload.type')
    await typeInto(user, 'Value 1', 'WORKFLOW_FAILED')
    await user.click(screen.getByRole('button', { name: 'Add condition' }))
    await typeInto(user, 'Field 2', 'payload.environment')
    await typeInto(user, 'Value 2', 'prod')
    await paste(user, 'Title', 'Failed')
    await user.click(screen.getByRole('button', { name: 'Save rule' }))
  }

  test('422 errors land under the condition node and field they name', async () => {
    withBuilderData()
    server.use(
      respond(createRule, 'post', createUrl, 422, {
        detail: [
          { loc: ['body', 'condition', 'and', 'args', 1, 'eq', 'value'], msg: 'Value is not allowed here', type: 'value_error' },
          { loc: ['body', 'presentation', 'title'], msg: 'Unknown placeholder', type: 'value_error' },
        ],
      }),
    )
    const { user, findByText, getByRole } = openAs(petraIn('member'), NEW_PATH)

    await fillMinimal(user)

    expect(await findByText('Unknown placeholder')).toBeInTheDocument()
    expect(within(getByRole('group', { name: 'Condition 2' })).getByText('Value is not allowed here')).toBeInTheDocument()
  })

  test.each([
    [400, "Couldn't read the rule. Reload the page and try again."],
    [403, "Couldn't save the rule. Only members and leads of this team can change its rules."],
    [404, "Couldn't save the rule. Something it points at no longer exists: Runbook not found"],
  ] as const)('%i shows why', async (status, message) => {
    withBuilderData()
    server.use(respond(createRule, 'post', createUrl, status, { detail: 'Runbook not found' }))
    const { user, findByRole } = openAs(petraIn('member'), NEW_PATH)

    await fillMinimal(user)

    expect(await findByRole('alert')).toHaveTextContent(message)
  })

  test.each([409, 501])('an undocumented %i shows the shared fallback', async (status) => {
    withBuilderData()
    server.use(http.post(createUrl, () => HttpResponse.json({ detail: 'x' }, { status })))
    const { user, findByRole } = openAs(petraIn('member'), NEW_PATH)

    await fillMinimal(user)

    expect(await findByRole('alert')).toHaveTextContent(
      status === 501 ? "This feature isn't available yet." : 'Something went wrong on the server (HTTP 409).',
    )
  })

  test('a viewer cannot open the new rule builder', async () => {
    withBuilderData()

    const { findByText, queryByRole } = openAs(petraIn('viewer'), NEW_PATH)

    expect(await findByText("You can't add rules here")).toBeInTheDocument()
    expect(queryByRole('button', { name: 'Save rule' })).not.toBeInTheDocument()
  })
})

describe('GET /rules/{id}', () => {
  test('fills the builder from the rule', async () => {
    const { findByRole, getByRole, getByTestId } = openEdit()

    expect(await findByRole('heading', { name: rule.name, level: 1 })).toBeInTheDocument()
    expect(getByRole('textbox', { name: 'Rule name' })).toHaveValue(rule.name)
    expect(getByTestId('condition-sentence')).toHaveTextContent(
      'type is WORKFLOW_FAILED and workflowName is order-settlement and environment is prod',
    )
    expect(await screen.findByRole('list', { name: 'Selected event schemas' })).toHaveTextContent('workflow v1')
    expect(getByRole('combobox', { name: 'Colour' })).toHaveTextContent('Red')
    expect(getByRole('list', { name: 'Fields that identify a problem' })).toHaveTextContent('payload.workflowId')
    expect(getByRole('button', { name: 'Save rule' })).toBeDisabled()
    expect(getByRole('figure', { name: 'Alert preview' })).toHaveTextContent('Settlement {{payload.workflowId}} failed at {{payload.step}}')
  })

  test("a rule of another team shows the 404 page", async () => {
    withBuilderData()
    server.use(respond(getRule, 'get', ruleUrl, 200, settlementsRule({ owner: { type: 'team', team_id: 'team-other' } })))

    const { findByText } = openAs(petraIn('member'), EDIT_PATH)

    expect(await findByText('Page not found')).toBeInTheDocument()
  })

  test("someone else's personal rule shows the 404 page under /me/rules, even for an admin", async () => {
    withBuilderData(null)
    server.use(respond(getRule, 'get', ruleUrl, 200, settlementsRule({ owner: { type: 'user', user_id: 'user-anna' } })))

    const { findByText } = openAs(petra('admin', []), `/me/rules/${rule.id}`)

    expect(await findByText('Page not found')).toBeInTheDocument()
  })

  test.each([
    [404, "This rule doesn't exist anymore. It may have been deleted."],
    [422, "Couldn't load this rule. Check the link and try again."],
  ] as const)('%i shows why', async (status, message) => {
    withBuilderData()
    server.use(
      status === 404
        ? respond(getRule, 'get', ruleUrl, 404, { detail: 'x' })
        : respond(getRule, 'get', ruleUrl, 422, { detail: [{ loc: ['path', 'rule_id'], msg: 'bad', type: 'uuid' }] }),
    )

    const { findByRole } = openAs(petraIn('member'), EDIT_PATH)

    expect(await findByRole('alert')).toHaveTextContent(message)
  })

  test('the 501 stub shows the shared fallback', async () => {
    withBuilderData()
    server.use(http.get(ruleUrl, () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole } = openAs(petraIn('member'), EDIT_PATH)

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('a viewer sees the rule read-only', async () => {
    const { findByRole, queryByRole, getByText } = openEdit('viewer')

    expect(await findByRole('textbox', { name: 'Rule name' })).toBeDisabled()
    expect(getByText('Only members and leads of this team can change its rules.')).toBeInTheDocument()
    expect(queryByRole('button', { name: 'Save rule' })).not.toBeInTheDocument()
    expect(queryByRole('button', { name: 'Delete rule' })).not.toBeInTheDocument()
    expect(queryByRole('button', { name: 'Add condition' })).not.toBeInTheDocument()
  })
})

describe('PATCH /rules/{id} (full edit)', () => {
  const url = getUpdateRuleUrl(rule.id)

  test('200 sends only what changed and keeps the builder open', async () => {
    server.use(respond(updateRule, 'patch', url, 200, { ...rule, name: 'Settlement failed' }))
    const patches = recordRequests('patch', url)
    const { user, findAllByText } = openEdit()

    await typeInto(user, 'Rule name', 'Settlement failed')
    await typeInto(user, 'Value 3', 'staging')
    await user.click(screen.getByRole('button', { name: 'Save rule' }))

    expect((await findAllByText('Rule saved')).length).toBeGreaterThan(0)
    await waitFor(() =>
      expect(patches.map(({ body }) => body)).toEqual([
        {
          name: 'Settlement failed',
          condition: {
            op: 'and',
            args: [
              { op: 'eq', field: 'payload.type', value: 'WORKFLOW_FAILED' },
              { op: 'eq', field: 'payload.workflowName', value: 'order-settlement' },
              { op: 'eq', field: 'payload.environment', value: 'staging' },
            ],
          },
        },
      ]),
    )
    expect(screen.getByRole('button', { name: 'Save rule' })).toBeDisabled()
  })

  test.each([
    [403, "Couldn't save the rule. Only members and leads of this team can change its rules."],
    [404, "Couldn't save the rule. Rule not found"],
  ] as const)('%i shows why', async (status, message) => {
    server.use(respond(updateRule, 'patch', url, status, { detail: 'Rule not found' }))
    const { user, findByRole } = openEdit()

    await typeInto(user, 'Rule name', 'Renamed')
    await user.click(screen.getByRole('button', { name: 'Save rule' }))

    expect(await findByRole('alert')).toHaveTextContent(message)
  })

  test('422 under a nested field', async () => {
    server.use(
      respond(updateRule, 'patch', url, 422, {
        detail: [{ loc: ['body', 'dedup', 'window_s'], msg: 'Input should be less than or equal to 86400', type: 'less_than_equal' }],
      }),
    )
    const { user, findByText } = openEdit()

    await typeInto(user, 'Rule name', 'Renamed')
    await user.click(screen.getByRole('button', { name: 'Save rule' }))

    expect(await findByText('Input should be less than or equal to 86400')).toBeInTheDocument()
  })

  test('leaving with unsaved changes asks first', async () => {
    server.use(respond(listRules, 'get', getListRulesUrl(), 200, [rule]))
    const { user, findByRole } = openEdit()

    await typeInto(user, 'Rule name', 'Renamed')
    await user.click(screen.getByRole('link', { name: 'Back to rules' }))

    const dialog = await findByRole('alertdialog', { name: 'Leave without saving?' })
    await user.click(within(dialog).getByRole('button', { name: 'Discard changes' }))
    expect(await findByRole('heading', { name: 'Rules', level: 1 })).toBeInTheDocument()
  })
})

describe('DELETE /rules/{id}', () => {
  const url = getDeleteRuleUrl(rule.id)

  async function confirmDelete() {
    const rendered = openEdit()
    await rendered.user.click(await rendered.findByRole('button', { name: 'Delete rule' }))
    const dialog = await rendered.findByRole('alertdialog', { name: `Delete ${rule.name}?` })
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Delete rule' }))
    return { ...rendered, dialog }
  }

  test('204 deletes, says so and opens the list', async () => {
    server.use(respond(deleteRule, 'delete', url, 204, undefined), respond(listRules, 'get', getListRulesUrl(), 200, []))

    const { findByText, findByRole } = await confirmDelete()

    expect(await findByText('Rule deleted')).toBeInTheDocument()
    expect(await findByRole('heading', { name: 'Rules', level: 1 })).toBeInTheDocument()
  })

  test('403 keeps the dialog open with the reason', async () => {
    server.use(respond(deleteRule, 'delete', url, 403, { detail: 'x' }))

    const { dialog } = await confirmDelete()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      "Couldn't delete the rule. Only members and leads of this team can change its rules.",
    )
  })

  test('an undocumented 409 shows the shared fallback', async () => {
    server.use(http.delete(url, () => HttpResponse.json({ detail: 'x' }, { status: 409 })))

    const { dialog } = await confirmDelete()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Something went wrong on the server (HTTP 409).')
  })
})

describe('POST /rules/test', () => {
  const url = getTestRuleUrl()
  const sample = '{"type": "WORKFLOW_FAILED", "workflowName": "order-settlement", "environment": "prod", "workflowId": "wf-8f21", "step": "reserve-funds", "error": {"message": "Timeout after 30 s"}}'

  async function test_(status?: number) {
    const rendered = openEdit()
    await rendered.findByRole('heading', { name: rule.name, level: 1 })
    await paste(rendered.user, 'Sample event payload (JSON)', sample)
    void status
    return rendered
  }

  test('matched: sends the condition and sample, previews the rendered alert', async () => {
    server.use(respond(testRule, 'post', url, 200, { matched: true, title: null }))
    const tests = recordRequests('post', url)

    const { findByText, getByRole } = await test_()

    expect(await findByText('Matches: this event would raise an alert.')).toBeInTheDocument()
    await waitFor(() =>
      expect(tests.at(-1)?.body).toEqual({
        condition: rule.condition,
        payload: JSON.parse(sample),
        source: 'test',
        severity: 'critical',
        schema_id: workflowSchema.id,
      }),
    )
    const preview = getByRole('figure', { name: 'Alert preview' })
    expect(preview).toHaveTextContent('Settlement wf-8f21 failed at reserve-funds')
    expect(preview).toHaveTextContent('Timeout after 30 s')
  })

  test('not matched', async () => {
    server.use(respond(testRule, 'post', url, 200, { matched: false }))

    const { findByText } = await test_()

    expect(await findByText("Doesn't match: this event would not raise an alert.")).toBeInTheDocument()
  })

  test('a sample that is not JSON is flagged and not sent', async () => {
    const tests = recordRequests('post', url)
    const rendered = openEdit()
    await rendered.findByRole('heading', { name: rule.name, level: 1 })

    await paste(rendered.user, 'Sample event payload (JSON)', '{"type": ')

    expect(await rendered.findByText(/The sample isn't valid JSON/)).toBeInTheDocument()
    expect(tests).toEqual([])
  })

  test.each([
    [400, "Couldn't read the rule. Reload the page and try again."],
    [422, "Couldn't test the rule. Field required"],
  ] as const)('%i shows why', async (status, message) => {
    server.use(
      status === 400
        ? respond(testRule, 'post', url, 400, { detail: 'x' })
        : respond(testRule, 'post', url, 422, { detail: [{ loc: ['body', 'payload'], msg: 'Field required', type: 'missing' }] }),
    )

    const { findByRole } = await test_()

    expect(await findByRole('alert')).toHaveTextContent(message)
  })

  test.each([
    [403, 'Something went wrong on the server (HTTP 403).'],
    [404, 'Something went wrong on the server (HTTP 404).'],
    [409, 'Something went wrong on the server (HTTP 409).'],
    [501, "This feature isn't available yet."],
  ] as const)('an undocumented %i shows the shared fallback', async (status, message) => {
    server.use(http.post(url, () => HttpResponse.json({ detail: 'x' }, { status })))

    const { findByRole } = await test_()

    expect(await findByRole('alert')).toHaveTextContent(message)
  })
})
