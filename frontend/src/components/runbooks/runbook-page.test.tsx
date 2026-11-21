import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import {
  deleteRunbook,
  getDeleteRunbookUrl,
  getGetRunbookUrl,
  getListRunbooksUrl,
  getParseRunbookUrl,
  getRunbook,
  getUpdateRunbookUrl,
  listRunbooks,
  parseRunbook,
  updateRunbook,
} from '@/api/generated/runbooks/runbooks'
import { respond } from '@/test/http'
import { example, parsedExamples, runbook } from '@/test/runbooks'
import { server } from '@/test/server'
import { openAs, petraIn, recordRequests } from '@/test/teams'
import { PARSE_DEBOUNCE_MS } from './use-parse-preview'

const saved = runbook('settlement-timeout', {
  title: 'Settlement timeout',
  format: 'structured',
  original: example('settlement-timeout').original,
  attach: parsedExamples['settlement-timeout'].attach,
  steps: parsedExamples['settlement-timeout'].steps,
})
const PATH = `/teams/settlements/runbooks/${saved.id}`

function loaded(value = saved) {
  return respond(getRunbook, 'get', getGetRunbookUrl(saved.id), 200, value)
}

function open(role: 'member' | 'lead' | 'viewer' = 'member') {
  return openAs(petraIn(role), PATH)
}

describe('GET /runbooks/{id}', () => {
  test('a member gets the form filled in and the saved steps without a parse request', async () => {
    const parses = recordRequests('post', '/api/runbooks/parse')
    server.use(loaded())

    open()

    expect(await screen.findByLabelText('Title')).toHaveValue('Settlement timeout')
    expect(screen.getByRole('heading', { level: 1, name: 'Settlement timeout' })).toBeInTheDocument()
    expect(screen.getByText('settlement-timeout', { selector: 'span' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Slug')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'YAML' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Runbook text')).toHaveValue(saved.original)
    expect(within(screen.getByRole('list', { name: 'Parsed steps' })).getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByRole('button', { name: 'Save runbook' })).toBeDisabled()
    await new Promise((resolve) => setTimeout(resolve, PARSE_DEBOUNCE_MS + 100))
    expect(parses).toHaveLength(0)
  })

  test('shows a skeleton while loading', async () => {
    server.use(http.get(getGetRunbookUrl(saved.id), () => delay('infinite')))

    open()

    expect(await screen.findByTestId('runbook-skeleton')).toBeInTheDocument()
  })

  test('a viewer reads the text and steps without any controls', async () => {
    server.use(loaded())

    open('viewer')

    expect(await screen.findByText('Only members and leads can change runbooks.')).toBeInTheDocument()
    expect(screen.getByText(/runbook: settlement-timeout/, { selector: 'pre' })).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Parsed steps' })).getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByText('YAML')).toBeInTheDocument()
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save runbook' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete runbook' })).not.toBeInTheDocument()
  })

  test('a runbook of another team is not shown under this team', async () => {
    server.use(loaded({ ...saved, team_id: 'team-other' }))

    open()

    expect(await screen.findByRole('alert')).toHaveTextContent('This runbook no longer exists.')
  })

  test('404 says the runbook is gone and links back to the list', async () => {
    server.use(respond(getRunbook, 'get', getGetRunbookUrl(saved.id), 404, { detail: 'Not found' }))

    open()

    expect(await screen.findByRole('alert')).toHaveTextContent('This runbook no longer exists.')
    expect(screen.getByRole('link', { name: 'Back to runbooks' })).toHaveAttribute('href', '/teams/settlements/runbooks')
  })

  test('422 says the link is broken', async () => {
    server.use(respond(getRunbook, 'get', getGetRunbookUrl(saved.id), 422, { detail: [] }))

    open()

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load this runbook. Check the link")
  })

  test('the 501 stub falls back to the shared message with Try again', async () => {
    server.use(http.get(getGetRunbookUrl(saved.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    open()

    expect(await screen.findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('PATCH /runbooks/{id}', () => {
  test('sends only the changed title, then shows it saved', async () => {
    const sent = recordRequests('patch', `/api/runbooks/${saved.id}`)
    server.use(
      loaded(),
      respond(updateRunbook, 'patch', getUpdateRunbookUrl(saved.id), 200, { ...saved, title: 'Settlement timeouts' }),
    )
    const { user } = open()

    await user.type(await screen.findByLabelText('Title'), 's')
    await user.click(screen.getByRole('button', { name: 'Save runbook' }))

    expect(await screen.findByText('Runbook saved')).toBeInTheDocument()
    await waitFor(() => expect(sent[0]?.body).toEqual({ title: 'Settlement timeouts' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Settlement timeouts' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save runbook' })).toBeDisabled()
  })

  test('a changed text is parsed again and saved with its format', async () => {
    const sent = recordRequests('patch', `/api/runbooks/${saved.id}`)
    const markdown = example('payments-error-rate')
    server.use(
      loaded(),
      respond(parseRunbook, 'post', getParseRunbookUrl(), 200, parsedExamples['payments-error-rate']),
      respond(updateRunbook, 'patch', getUpdateRunbookUrl(saved.id), 200, {
        ...saved,
        format: 'markdown',
        original: markdown.original,
        attach: null,
        steps: parsedExamples['payments-error-rate'].steps,
      }),
    )
    const { user } = open()

    await screen.findByLabelText('Title')
    await user.click(screen.getByRole('button', { name: 'Insert example' }))
    // The saved text is the YAML sample, so the example replaces it without asking.
    await user.click(await screen.findByRole('menuitem', { name: markdown.label }))

    await waitFor(() =>
      expect(within(screen.getByRole('list', { name: 'Parsed steps' })).getAllByRole('listitem')).toHaveLength(4),
      { timeout: 3000 },
    )
    await user.click(screen.getByRole('button', { name: 'Save runbook' }))

    // Sonner keeps toasts across tests, so wait for the saved form instead of the toast.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save runbook' })).toBeDisabled())
    expect(sent[0]?.body).toEqual({ format: 'markdown', original: markdown.original })
  })

  test('422 puts the error under the field it names', async () => {
    server.use(
      loaded(),
      respond(updateRunbook, 'patch', getUpdateRunbookUrl(saved.id), 422, {
        detail: [{ loc: ['body', 'title'], msg: 'Title is too long', type: 'string_too_long' }],
      }),
    )
    const { user } = open()

    await user.type(await screen.findByLabelText('Title'), 'x')
    await user.click(screen.getByRole('button', { name: 'Save runbook' }))

    const field = screen.getByText('Title', { selector: 'label' }).closest('[data-slot="field"]')
    if (!(field instanceof HTMLElement)) throw new Error('no title field')
    expect(await within(field).findByText('Title is too long')).toBeInTheDocument()
  })

  test.each([
    [400, "Couldn't save the runbook. Reload the page and try again."],
    [403, "You can't change this team's runbooks. Ask a team lead to make you a member."],
    [404, 'This runbook no longer exists. Go back to the runbook list.'],
  ] as const)('%i shows a form error', async (status, message) => {
    server.use(loaded(), respond(updateRunbook, 'patch', getUpdateRunbookUrl(saved.id), status, { detail: 'No' }))
    const { user } = open()

    await user.type(await screen.findByLabelText('Title'), 'x')
    await user.click(screen.getByRole('button', { name: 'Save runbook' }))

    expect(await screen.findByText(message)).toHaveAttribute('role', 'alert')
  })

  test('the 501 stub falls back to the shared message', async () => {
    server.use(
      loaded(),
      http.patch(getUpdateRunbookUrl(saved.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    const { user } = open()

    await user.type(await screen.findByLabelText('Title'), 'x')
    await user.click(screen.getByRole('button', { name: 'Save runbook' }))

    expect(await screen.findByText("This feature isn't available yet.")).toHaveAttribute('role', 'alert')
  })
})

describe('DELETE /runbooks/{id}', () => {
  async function confirmDelete(user: ReturnType<typeof open>['user']) {
    await user.click(await screen.findByRole('button', { name: 'Delete runbook' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Delete Settlement timeout?' })
    await user.click(within(dialog).getByRole('button', { name: 'Delete runbook' }))
    return dialog
  }

  test('asks, deletes and goes back to the list', async () => {
    server.use(
      loaded(),
      respond(deleteRunbook, 'delete', getDeleteRunbookUrl(saved.id), 204, undefined),
      respond(listRunbooks, 'get', getListRunbooksUrl(), 200, []),
    )
    const { user, router } = open()

    await confirmDelete(user)

    expect(await screen.findByText('Settlement timeout deleted')).toBeInTheDocument()
    await waitFor(() => expect(router.state.location.pathname).toBe('/teams/settlements/runbooks'))
  })

  test('Cancel keeps the runbook', async () => {
    const sent = recordRequests('delete', `/api/runbooks/${saved.id}`)
    server.use(loaded())
    const { user } = open()

    await user.click(await screen.findByRole('button', { name: 'Delete runbook' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Delete Settlement timeout?' })
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(sent).toHaveLength(0)
  })

  test.each([
    [403, "You can't delete this team's runbooks. Ask a team lead to make you a member."],
    [404, 'This runbook no longer exists. Go back to the runbook list.'],
  ] as const)('%i keeps the dialog open with the reason', async (status, message) => {
    server.use(
      loaded(),
      respond(deleteRunbook, 'delete', getDeleteRunbookUrl(saved.id), status, { detail: 'No' }),
      respond(listRunbooks, 'get', getListRunbooksUrl(), 200, [saved]),
    )
    const { user } = open()

    const dialog = await confirmDelete(user)

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(message)
  })

  test('422 keeps the dialog open with the reason', async () => {
    server.use(loaded(), respond(deleteRunbook, 'delete', getDeleteRunbookUrl(saved.id), 422, { detail: [] }))
    const { user } = open()

    const dialog = await confirmDelete(user)

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("Couldn't delete this runbook.")
  })

  test('the 501 stub falls back to the shared message', async () => {
    server.use(
      loaded(),
      http.delete(getDeleteRunbookUrl(saved.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    const { user } = open()

    const dialog = await confirmDelete(user)

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
