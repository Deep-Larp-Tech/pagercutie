import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import type { RunbookParseResult } from '@/api/generated/model'
import {
  createRunbook,
  getCreateRunbookUrl,
  getGetRunbookUrl,
  getListRunbooksUrl,
  getParseRunbookUrl,
  getRunbook,
  listRunbooks,
  parseRunbook,
} from '@/api/generated/runbooks/runbooks'
import { ParseRunbookBody } from '@/api/generated/runbooks/runbooks.zod'
import { runbookExamples, type RunbookExample } from '@/lib/runbook-examples'
import { respond } from '@/test/http'
import { example, parsedExamples, runbook } from '@/test/runbooks'
import { server } from '@/test/server'
import { openAs, petraIn, recordRequests, settlements } from '@/test/teams'
import { PARSE_DEBOUNCE_MS } from './use-parse-preview'

const PATH = '/teams/settlements/runbooks/new'

/** Wait for the debounced parse answer, which arrives after `PARSE_DEBOUNCE_MS`. */
const PARSED = { timeout: 3000 }

/** Answers `POST /runbooks/parse` with the §6.2 parse result for a sample text, and one manual step otherwise. */
function parsing() {
  return http.post(getParseRunbookUrl(), async ({ request }) => {
    const body = ParseRunbookBody.parse(await request.json())
    const sample = runbookExamples.find((candidate) => candidate.original === body.original)
    const result: RunbookParseResult =
      sample === undefined
        ? { attach: null, steps: [{ action: 'manual', text: body.original }], warnings: [] }
        : parsedExamples[sample.id]
    return HttpResponse.json(result)
  })
}

function open(role: 'member' | 'viewer' = 'member') {
  server.use(parsing())
  return openAs(petraIn(role), PATH)
}

function textArea() {
  return screen.getByLabelText('Runbook text')
}

/** The error text under the field labelled `label`. */
function fieldError(label: string) {
  const field = screen.getByText(label, { selector: 'label' }).closest('[data-slot="field"]')
  if (!(field instanceof HTMLElement)) throw new Error(`no field labelled ${label}`)
  return within(field).getByText((_, element) => element?.getAttribute('data-slot') === 'field-error')
}

async function insert(user: ReturnType<typeof open>['user'], id: RunbookExample['id']) {
  await user.click(screen.getByRole('button', { name: 'Insert example' }))
  await user.click(await screen.findByRole('menuitem', { name: example(id).label }))
}

/** Fills a valid form and submits it. */
async function fillAndSave(user: ReturnType<typeof open>['user']) {
  await user.type(await screen.findByLabelText('Title'), 'Settlement timeout')
  await insert(user, 'settlement-timeout')
  await user.click(screen.getByRole('button', { name: 'Save runbook' }))
}

const created = runbook('settlement-timeout', {
  title: 'Settlement timeout',
  format: 'structured',
  original: example('settlement-timeout').original,
  attach: parsedExamples['settlement-timeout'].attach,
  steps: parsedExamples['settlement-timeout'].steps,
})

describe('the new runbook form', () => {
  test('the slug follows the title until it is edited', async () => {
    const { user } = open()

    await user.type(await screen.findByLabelText('Title'), 'Settlement Timeout!')
    expect(screen.getByLabelText('Slug')).toHaveValue('settlement-timeout')

    await user.type(screen.getByLabelText('Slug'), '-v2')
    await user.type(screen.getByLabelText('Title'), ' again')
    expect(screen.getByLabelText('Slug')).toHaveValue('settlement-timeout-v2')
  })

  test('the format is picked with a segmented control of the four formats, YAML first', async () => {
    const { user } = open()

    const group = await screen.findByRole('group', { name: 'Format' })
    const options = within(group).getAllByRole('button')
    expect(options.map((option) => option.textContent)).toEqual(['YAML', 'Markdown', 'Free text', 'Link'])
    expect(within(group).getByRole('button', { name: 'YAML' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(within(group).getByRole('button', { name: 'Link' }))
    expect(within(group).getByRole('button', { name: 'Link' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('A link to a wiki or Confluence page, shown as one step: open the runbook.')).toBeVisible()
  })

  test('an empty form says what is missing and sends nothing', async () => {
    const sent = recordRequests('post', '/api/runbooks')
    const { user } = open()

    await user.click(await screen.findByRole('button', { name: 'Save runbook' }))

    expect(fieldError('Title')).toHaveTextContent('Enter a title.')
    expect(fieldError('Slug')).toHaveTextContent('Enter a slug.')
    expect(fieldError('Runbook text')).toHaveTextContent('Paste the runbook text or insert an example.')
    expect(sent).toHaveLength(0)
  })

  test('a slug outside the pattern is refused before sending', async () => {
    const { user } = open()

    await user.type(await screen.findByLabelText('Slug'), 'Not A Slug')
    await user.click(screen.getByRole('button', { name: 'Save runbook' }))

    expect(fieldError('Slug')).toHaveTextContent('Use lower case letters and digits, joined by single hyphens')
  })

  test('a viewer opening the page sees who can add runbooks and no form', async () => {
    open('viewer')

    expect(await screen.findByText('Only members and leads can change runbooks.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Runbook text')).not.toBeInTheDocument()
  })
})

describe('insert example (RUN-8)', () => {
  test('fills format, text, title and slug from the YAML sample', async () => {
    const { user } = open()
    await screen.findByLabelText('Title')

    await insert(user, 'settlement-timeout')

    expect(textArea()).toHaveValue(example('settlement-timeout').original)
    expect(screen.getByRole('button', { name: 'YAML' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Title')).toHaveValue('Settlement timeout')
    expect(screen.getByLabelText('Slug')).toHaveValue('settlement-timeout')
  })

  test('keeps a title the user already typed', async () => {
    const { user } = open()

    await user.type(await screen.findByLabelText('Title'), 'Payments')
    await insert(user, 'payments-error-rate')

    expect(screen.getByLabelText('Title')).toHaveValue('Payments')
    expect(screen.getByRole('button', { name: 'Markdown' })).toHaveAttribute('aria-pressed', 'true')
  })

  test('asks before replacing text the user wrote', async () => {
    const { user } = open()

    await user.type(await screen.findByLabelText('Runbook text'), 'my own steps')
    await insert(user, 'pricing-latency')

    const dialog = await screen.findByRole('alertdialog', { name: 'Replace the runbook text?' })
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(textArea()).toHaveValue('my own steps')

    await insert(user, 'pricing-latency')
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Replace text' }),
    )
    expect(textArea()).toHaveValue(example('pricing-latency').original)
    expect(screen.getByRole('button', { name: 'Free text' })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('POST /runbooks/parse', () => {
  test('the YAML sample shows three actions, placeholders, the approval badge, the guard and the condition', async () => {
    const { user } = open()
    await screen.findByLabelText('Title')

    await insert(user, 'settlement-timeout')

    const list = await screen.findByRole('list', { name: 'Parsed steps' }, PARSED)
    const steps = within(list).getAllByRole('listitem')
    expect(steps).toHaveLength(3)
    expect(steps[0]).toHaveTextContent('Check a URL')
    expect(steps[0]).toHaveTextContent('Question: Is counterparty-service healthy?')
    expect(steps[0]).toHaveTextContent('http://counterparty-service/health')
    expect(steps[0]).toHaveTextContent('Runs without approval.')
    expect(steps[1]).toHaveTextContent('Retry workflow')
    expect(within(steps[1] as HTMLElement).getByText('{{workflowId}}')).toHaveAttribute('data-placeholder')
    expect(steps[2]).toHaveTextContent('Escalate')
    expect(steps[2]).toHaveTextContent('counterparty-support')
    expect(steps[2]).toHaveTextContent('Only after step 2 (Retry workflow) has failed twice.')
    expect(steps[2]).toHaveTextContent('A team lead approves it before it runs.')
    expect(within(list).getAllByText('Needs approval')).toHaveLength(1)
    expect(within(steps[2] as HTMLElement).getByText('Needs approval')).toBeVisible()
    expect(screen.getByText('type = WORKFLOW_FAILED and error.code = TIMEOUT')).toBeVisible()
  })

  test('the Markdown sample shows four manual steps and the warning', async () => {
    const { user } = open()
    await screen.findByLabelText('Title')

    await insert(user, 'payments-error-rate')

    const list = await screen.findByRole('list', { name: 'Parsed steps' }, PARSED)
    const steps = within(list).getAllByRole('listitem')
    expect(steps).toHaveLength(4)
    for (const step of steps) expect(step).toHaveTextContent('Manual step')
    expect(steps[1]).toHaveTextContent('fail traffic over to the other region')
    expect(screen.getByTestId('parse-warnings')).toHaveTextContent('Markdown list items became manual steps.')
    expect(screen.getByText('No condition in the text. Rules that name this runbook show it on their alerts.')).toBeVisible()
  })

  test('the free-text sample shows one manual step with the whole text', async () => {
    const { user } = open()
    await screen.findByLabelText('Title')

    await insert(user, 'pricing-latency')

    const list = await screen.findByRole('list', { name: 'Parsed steps' }, PARSED)
    const steps = within(list).getAllByRole('listitem')
    expect(steps).toHaveLength(1)
    expect(steps[0]).toHaveTextContent("When pricing latency goes over a second, it's usually the cache.")
  })

  test('shows a skeleton while the first answer loads', async () => {
    const { user } = open()
    server.use(http.post(getParseRunbookUrl(), () => delay('infinite')))

    await user.type(await screen.findByLabelText('Runbook text'), 'x')

    expect(await screen.findByTestId('preview-skeleton', {}, PARSED)).toBeInTheDocument()
  })

  test('typing sends one parse request with the final text after the pause', async () => {
    const sent = recordRequests('post', '/api/runbooks/parse')
    const { user } = open()

    await user.click(await screen.findByRole('button', { name: 'Markdown' }))
    await user.type(textArea(), '1. Check it')

    expect(await screen.findByRole('list', { name: 'Parsed steps' }, PARSED)).toHaveTextContent('1. Check it')
    await new Promise((resolve) => setTimeout(resolve, PARSE_DEBOUNCE_MS + 100))
    expect(sent).toHaveLength(1)
    await waitFor(() => expect(sent[0]?.body).toEqual({ format: 'markdown', original: '1. Check it' }))
  })

  test('sends nothing while the text is empty', async () => {
    const sent = recordRequests('post', '/api/runbooks/parse')
    open()

    expect(await screen.findByText('Paste a runbook or insert an example to see its steps.')).toBeInTheDocument()
    await new Promise((resolve) => setTimeout(resolve, PARSE_DEBOUNCE_MS + 100))
    expect(sent).toHaveLength(0)
  })

  test('422 lists why the text does not fit its format', async () => {
    const { user } = open()
    server.use(
      respond(parseRunbook, 'post', getParseRunbookUrl(), 422, {
        detail: [{ loc: ['body', 'original'], msg: 'steps.0.action: unknown action reboot', type: 'value_error' }],
      }),
    )

    await user.type(await screen.findByLabelText('Runbook text'), 'steps: reboot')

    const alert = await screen.findByRole('alert', {}, PARSED)
    expect(alert).toHaveTextContent("Couldn't read this runbook")
    expect(alert).toHaveTextContent('steps.0.action: unknown action reboot')
  })

  test('400 says the text could not be read', async () => {
    const { user } = open()
    server.use(respond(parseRunbook, 'post', getParseRunbookUrl(), 400, { detail: 'Bad body' }))

    await user.type(await screen.findByLabelText('Runbook text'), 'x')

    expect(await screen.findByRole('alert', {}, PARSED)).toHaveTextContent("Couldn't read the text.")
  })

  test('the 501 stub says the preview is not available yet', async () => {
    const { user } = open()
    server.use(http.post(getParseRunbookUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    await user.type(await screen.findByLabelText('Runbook text'), 'x')

    expect(await screen.findByRole('alert', {}, PARSED)).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('POST /runbooks', () => {
  test('saves the runbook for the team, without a condition, and opens it', async () => {
    const sent = recordRequests('post', '/api/runbooks')
    server.use(
      respond(createRunbook, 'post', getCreateRunbookUrl(), 201, created),
      respond(getRunbook, 'get', getGetRunbookUrl(created.id), 200, created),
    )
    const { user, router } = open()

    await fillAndSave(user)

    expect(await screen.findByText('Settlement timeout saved')).toBeVisible()
    await waitFor(() => expect(router.state.location.pathname).toBe(`/teams/settlements/runbooks/${created.id}`))
    expect(sent[0]?.body).toEqual({
      title: 'Settlement timeout',
      slug: 'settlement-timeout',
      team_id: settlements.id,
      format: 'structured',
      original: example('settlement-timeout').original,
    })
  })

  test('409 puts the duplicate slug under the slug field', async () => {
    server.use(respond(createRunbook, 'post', getCreateRunbookUrl(), 409, { detail: 'Slug taken' }))
    const { user } = open()

    await fillAndSave(user)

    await waitFor(() =>
      expect(fieldError('Slug')).toHaveTextContent('Another runbook already uses this slug. Pick another one.'),
    )
  })

  test('422 puts invalid YAML under the runbook text', async () => {
    server.use(
      respond(createRunbook, 'post', getCreateRunbookUrl(), 422, {
        detail: [{ loc: ['body', 'original'], msg: 'Not valid YAML of the step model', type: 'value_error' }],
      }),
    )
    const { user } = open()

    await fillAndSave(user)

    await waitFor(() => expect(fieldError('Runbook text')).toHaveTextContent('Not valid YAML of the step model'))
  })

  test.each([
    [400, "Couldn't save the runbook. Reload the page and try again."],
    [403, "You can't change this team's runbooks. Ask a team lead to make you a member."],
    [404, 'This team no longer exists. Pick another team from the switcher.'],
  ] as const)('%i shows a form error', async (status, message) => {
    server.use(respond(createRunbook, 'post', getCreateRunbookUrl(), status, { detail: 'No' }))
    const { user } = open()

    await fillAndSave(user)

    expect(await screen.findByText(message)).toHaveAttribute('role', 'alert')
  })

  test('the 501 stub falls back to the shared message', async () => {
    server.use(http.post(getCreateRunbookUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const { user } = open()

    await fillAndSave(user)

    expect(await screen.findByText("This feature isn't available yet.")).toHaveAttribute('role', 'alert')
  })
})

describe('unsaved changes', () => {
  test('leaving with unsaved changes asks first; Cancel stays, Discard changes leaves', async () => {
    server.use(respond(listRunbooks, 'get', getListRunbooksUrl(), 200, []))
    const { user, router } = open()

    await user.type(await screen.findByLabelText('Title'), 'Half done')
    await user.click(screen.getByRole('link', { name: 'Cancel' }))

    const dialog = await screen.findByRole('alertdialog', { name: 'Leave without saving?' })
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(router.state.location.pathname).toBe(PATH)
    expect(screen.getByLabelText('Title')).toHaveValue('Half done')

    await user.click(screen.getByRole('link', { name: 'Cancel' }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Discard changes' }),
    )
    await waitFor(() => expect(router.state.location.pathname).toBe('/teams/settlements/runbooks'))
  })

  test('an untouched form leaves without asking', async () => {
    server.use(respond(listRunbooks, 'get', getListRunbooksUrl(), 200, []))
    const { user, router } = open()

    await user.click(await screen.findByRole('link', { name: 'Cancel' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/teams/settlements/runbooks'))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })
})
