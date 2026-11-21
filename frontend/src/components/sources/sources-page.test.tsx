import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import type { SourceRead } from '@/api/generated/model'
import {
  createSource,
  deleteSource,
  getCreateSourceUrl,
  getDeleteSourceUrl,
  getGetSourceUrl,
  getListSourcesUrl,
  getRotateSourceTokenUrl,
  getSource,
  getUpdateSourceUrl,
  listSources,
  rotateSourceToken,
  updateSource,
} from '@/api/generated/sources/sources'
import { respond } from '@/test/http'
import { server } from '@/test/server'
import { source } from '@/test/sources'
import { openAs, petraIn, recordRequests, settlements } from '@/test/teams'

const PATH = '/teams/settlements/sources'
const lead = petraIn('lead')
const payments = source('payments-webhook', 'Payments webhook')
const TOKEN = 'pc_live_9f8e7d6c5b4a'

function withSources(sources: SourceRead[]) {
  server.use(respond(listSources, 'get', getListSourcesUrl(), 200, sources))
}

function open(role: 'lead' | 'member' | 'viewer' = 'lead') {
  return openAs(role === 'lead' ? lead : petraIn(role), PATH)
}

type Rendered = ReturnType<typeof open>

async function rowAction(rendered: Rendered, name: string, action: string) {
  await rendered.user.click(await screen.findByRole('button', { name: `Actions for ${name}` }))
  await rendered.user.click(await screen.findByRole('menuitem', { name: action }))
}

/** The error text under the field labelled `label` inside `container`. */
function fieldError(container: HTMLElement, label: string) {
  const field = within(container).getByText(label, { selector: 'label' }).closest('[data-slot="field"]')
  if (!(field instanceof HTMLElement)) throw new Error(`no field labelled ${label}`)
  return within(field).getByText((_, element) => element?.getAttribute('data-slot') === 'field-error')
}

async function pick(rendered: Rendered, combobox: HTMLElement, option: string) {
  await rendered.user.click(combobox)
  await rendered.user.click(await screen.findByRole('option', { name: option }))
}

async function openNewSource(rendered: Rendered) {
  await rendered.user.click(await screen.findByRole('button', { name: 'New source' }))
  return screen.findByRole('dialog', { name: 'New source' })
}

/** Fills the name of the New source dialog; the slug follows it. */
async function fillName(rendered: Rendered, dialog: HTMLElement, name = 'Payments webhook') {
  await rendered.user.type(within(dialog).getByLabelText('Name'), name)
}

describe('GET /sources', () => {
  test('lists name, slug, type, ingest URL, token status and the enabled switch', async () => {
    const stream = source('ledger-ws', 'Ledger stream', { type: 'websocket', enabled: false, ingest_url: '/ingest/ledger-ws/ws' })
    withSources([payments, stream])
    open()

    await screen.findByText('Ledger stream')
    const rows = within(screen.getByRole('table', { name: 'Sources' })).getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('Payments webhookpayments-webhookWebhook/ingest/payments-webhookSet')
    expect(rows[1]).toHaveTextContent('Ledger streamledger-wsWebSocket/ingest/ledger-ws/wsSet')
    expect(screen.getByRole('switch', { name: 'Accept events from Payments webhook' })).toBeChecked()
    expect(screen.getByRole('switch', { name: 'Accept events from Ledger stream' })).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Actions for Ledger stream' })).toBeInTheDocument()
  })

  test('a source without a token says so and offers Create token', async () => {
    withSources([source('ledger', 'Ledger', { has_token: false })])
    const rendered = open()

    const row = await screen.findByRole('row', { name: /Ledger/ })
    expect(row).toHaveTextContent('No token yet')
    expect(within(row).getByRole('button', { name: 'Create token for Ledger' })).toBeInTheDocument()
    await rendered.user.click(within(row).getByRole('button', { name: 'Actions for Ledger' }))
    expect(await screen.findByRole('menuitem', { name: 'Create token' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Rotate token' })).not.toBeInTheDocument()
  })

  test('a source with a token offers Rotate token', async () => {
    withSources([payments])
    const rendered = open()

    const row = await screen.findByRole('row', { name: /Payments webhook/ })
    expect(row).not.toHaveTextContent('No token yet')
    expect(within(row).queryByRole('button', { name: /Create token/ })).not.toBeInTheDocument()
    await rendered.user.click(within(row).getByRole('button', { name: 'Actions for Payments webhook' }))
    expect(await screen.findByRole('menuitem', { name: 'Rotate token' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Create token' })).not.toBeInTheDocument()
  })

  test('copies the ingest URL', async () => {
    withSources([payments])
    const rendered = open()

    await rendered.user.click(await screen.findByRole('button', { name: 'Copy ingest URL of Payments webhook' }))

    expect(await navigator.clipboard.readText()).toBe('/ingest/payments-webhook')
    expect(screen.getByText('Copied')).toBeInTheDocument()
  })

  test('shows skeleton rows while loading', async () => {
    server.use(http.get(getListSourcesUrl(), () => delay('infinite')))
    open()

    expect(await screen.findAllByTestId('skeleton-row')).toHaveLength(5)
  })

  test('shows an empty state when the team has no sources', async () => {
    withSources([])
    open()

    expect(await screen.findByText('No sources yet')).toBeInTheDocument()
  })

  test('422 shows the error state', async () => {
    server.use(respond(listSources, 'get', getListSourcesUrl(), 422, { detail: [] }))
    open()

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load sources")
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.get(getListSourcesUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    open()

    expect(await screen.findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('a viewer sees the list read-only', async () => {
    withSources([payments, source('ledger', 'Ledger', { has_token: false })])
    open('viewer')

    await screen.findByText('Payments webhook')
    const rows = within(screen.getByRole('table', { name: 'Sources' })).getAllByRole('row')
    expect(rows[1]).toHaveTextContent('On')
    expect(rows[2]).toHaveTextContent('No token yet')
    expect(screen.queryByRole('button', { name: /Create token/ })).not.toBeInTheDocument()
    expect(screen.getByText('Only members and leads can change this.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New source' })).not.toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Actions for/ })).not.toBeInTheDocument()
  })

  test('a member gets the same controls as a lead', async () => {
    withSources([payments])
    open('member')

    expect(await screen.findByRole('button', { name: 'New source' })).toBeInTheDocument()
    expect(await screen.findByRole('switch', { name: 'Accept events from Payments webhook' })).toBeInTheDocument()
  })
})

describe('POST /sources', () => {
  test('derives the slug from the name, creates a source, then shows its first token once', async () => {
    withSources([])
    const created = source('payments-webhook', 'Payments webhook', { has_token: false })
    server.use(
      respond(createSource, 'post', getCreateSourceUrl(), 201, created),
      respond(rotateSourceToken, 'post', getRotateSourceTokenUrl(created.id), 200, { token: TOKEN }),
    )
    const sent = recordRequests('post', getCreateSourceUrl())
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillName(rendered, dialog)
    expect(within(dialog).getByLabelText('Slug')).toHaveValue('payments-webhook')
    withSources([created])
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    await waitFor(() =>
      expect(sent[0]?.body).toEqual({
        name: 'Payments webhook',
        slug: 'payments-webhook',
        type: 'webhook',
        team_id: settlements.id,
        severity: { field: null, values: {}, default: 'info' },
        enabled: true,
      }),
    )
    const step = await screen.findByRole('dialog', { name: 'Payments webhook added' })
    withSources([{ ...created, has_token: true }])
    await rendered.user.click(within(step).getByRole('button', { name: 'Create token' }))

    expect(await within(step).findByText('This token is shown only once.')).toBeInTheDocument()
    expect(within(step).getByLabelText('Ingest token')).toHaveValue(TOKEN)
    expect(within(step).getByLabelText('Send a test event')).toHaveTextContent(
      `curl -X POST '${window.location.origin}/ingest/payments-webhook'`,
    )
    expect(within(step).getByLabelText('Send a test event')).toHaveTextContent(`Authorization: Bearer ${TOKEN}`)

    await rendered.user.click(within(step).getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.queryByDisplayValue(TOKEN)).not.toBeInTheDocument()
    expect(await screen.findByRole('row', { name: /Payments webhook/ })).toHaveTextContent('Set')
  })

  test('sends the type, a severity mapping and enabled', async () => {
    withSources([])
    server.use(respond(createSource, 'post', getCreateSourceUrl(), 201, payments))
    const sent = recordRequests('post', getCreateSourceUrl())
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await rendered.user.type(within(dialog).getByLabelText('Name'), 'Ledger')
    await pick(rendered, within(dialog).getByRole('combobox', { name: 'Type' }), 'WebSocket')
    await rendered.user.type(within(dialog).getByLabelText('Severity field'), 'level')
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add value' }))
    await rendered.user.type(within(dialog).getByLabelText('Severity value 1'), 'FATAL')
    await pick(rendered, within(dialog).getByRole('combobox', { name: 'Severity for value 1' }), 'Critical')
    await rendered.user.click(within(dialog).getByRole('switch'))
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    await waitFor(() =>
      expect(sent[0]?.body).toEqual({
        name: 'Ledger',
        slug: 'ledger',
        type: 'websocket',
        team_id: settlements.id,
        severity: { field: 'level', values: { FATAL: 'critical' }, default: 'info' },
        enabled: false,
      }),
    )
  })

  test('checks the form before sending: a severity field for listed values, no repeated values', async () => {
    withSources([])
    const rendered = open()
    const dialog = await openNewSource(rendered)
    await rendered.user.type(within(dialog).getByLabelText('Name'), 'Ledger')
    const addValue = within(dialog).getByRole('button', { name: 'Add value' })
    await rendered.user.click(addValue)
    await rendered.user.click(addValue)
    await rendered.user.type(within(dialog).getByLabelText('Severity value 1'), 'FATAL')
    await rendered.user.type(within(dialog).getByLabelText('Severity value 2'), 'FATAL')

    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    expect(await within(dialog).findByText('Enter the field that holds the severity, or remove the values below.')).toBeInTheDocument()
    expect(within(dialog).getByText('This value is already in the list.')).toBeInTheDocument()
  })

  test('explains schema matching with a link to the team schemas', async () => {
    withSources([])
    const rendered = open()
    const dialog = await openNewSource(rendered)

    expect(dialog).toHaveTextContent("Each event is checked against the latest version of each of this team's event schemas")
    expect(within(dialog).getByRole('link', { name: 'event schemas' })).toHaveAttribute('href', '/teams/settlements/schemas')
  })

  test('409 shows the duplicate slug under Slug', async () => {
    withSources([])
    server.use(respond(createSource, 'post', getCreateSourceUrl(), 409, { detail: 'Slug taken' }))
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillName(rendered, dialog)
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    await waitFor(() => expect(fieldError(dialog, 'Slug')).toHaveTextContent('Another source already uses this slug.'))
  })

  test('422 puts each error under its field, including a nested severity path', async () => {
    withSources([])
    server.use(
      respond(createSource, 'post', getCreateSourceUrl(), 422, {
        detail: [
          { loc: ['body', 'name'], msg: 'Name is reserved', type: 'value_error' },
          { loc: ['body', 'severity', 'field'], msg: 'Not a field path', type: 'value_error' },
        ],
      }),
    )
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillName(rendered, dialog)
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    await waitFor(() => expect(fieldError(dialog, 'Name')).toHaveTextContent('Name is reserved'))
    expect(fieldError(dialog, 'Severity field')).toHaveTextContent('Not a field path')
  })

  test.each([
    [400, "Couldn't save the source. Reload the page and try again."],
    [403, 'Only members and leads can add sources.'],
    [404, 'The team no longer exists.'],
  ] as const)('%i shows a form error', async (status, message) => {
    withSources([])
    server.use(respond(createSource, 'post', getCreateSourceUrl(), status, { detail: 'x' }))
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillName(rendered, dialog)
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(message)
  })

  test('the 501 stub shows the shared fallback in the dialog', async () => {
    withSources([])
    server.use(http.post(getCreateSourceUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillName(rendered, dialog)
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('GET and PATCH /sources/{id}', () => {
  test('Edit source loads the source and sends only the changed name', async () => {
    withSources([payments])
    server.use(
      respond(getSource, 'get', getGetSourceUrl(payments.id), 200, payments),
      respond(updateSource, 'patch', getUpdateSourceUrl(payments.id), 200, { ...payments, name: 'Card payments' }),
    )
    const sent = recordRequests('patch', getUpdateSourceUrl(payments.id))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Edit source')
    const dialog = await screen.findByRole('dialog', { name: 'Edit source' })
    const name = await within(dialog).findByLabelText('Name')
    expect(within(dialog).queryByLabelText('Slug')).not.toBeInTheDocument()
    await rendered.user.clear(name)
    await rendered.user.type(name, 'Card payments')
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(sent[0]?.body).toEqual({ name: 'Card payments' }))
    expect(await screen.findByText('Card payments saved')).toBeInTheDocument()
  })

  test('GET 404 says the source is gone', async () => {
    withSources([payments])
    server.use(respond(getSource, 'get', getGetSourceUrl(payments.id), 404, { detail: 'Not found' }))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Edit source')

    const dialog = await screen.findByRole('dialog', { name: 'Edit source' })
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This source no longer exists.')
  })

  test('GET 501 shows the shared fallback', async () => {
    withSources([payments])
    server.use(http.get(getGetSourceUrl(payments.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Edit source')

    const dialog = await screen.findByRole('dialog', { name: 'Edit source' })
    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test.each([
    [422, 'Name', 'Too long'],
    [403, null, 'Only members and leads can change sources.'],
    [404, null, 'This source no longer exists.'],
  ] as const)('PATCH %i shows its error', async (status, field, message) => {
    withSources([payments])
    server.use(
      respond(getSource, 'get', getGetSourceUrl(payments.id), 200, payments),
      status === 422
        ? respond(updateSource, 'patch', getUpdateSourceUrl(payments.id), 422, {
            detail: [{ loc: ['body', 'name'], msg: message, type: 'value_error' }],
          })
        : respond(updateSource, 'patch', getUpdateSourceUrl(payments.id), status, { detail: 'x' }),
    )
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Edit source')
    const dialog = await screen.findByRole('dialog', { name: 'Edit source' })
    await rendered.user.type(await within(dialog).findByLabelText('Name'), ' 2')
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    if (field === null) expect(await within(dialog).findByRole('alert')).toHaveTextContent(message)
    else await waitFor(() => expect(fieldError(dialog, field)).toHaveTextContent(message))
  })

  test('PATCH 501 shows the shared fallback', async () => {
    withSources([payments])
    server.use(
      respond(getSource, 'get', getGetSourceUrl(payments.id), 200, payments),
      http.patch(getUpdateSourceUrl(payments.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Edit source')
    const dialog = await screen.findByRole('dialog', { name: 'Edit source' })
    await rendered.user.type(await within(dialog).findByLabelText('Name'), ' 2')
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('the enabled switch sends only enabled', async () => {
    withSources([payments])
    server.use(respond(updateSource, 'patch', getUpdateSourceUrl(payments.id), 200, { ...payments, enabled: false }))
    const sent = recordRequests('patch', getUpdateSourceUrl(payments.id))
    const rendered = open()

    await rendered.user.click(await screen.findByRole('switch', { name: 'Accept events from Payments webhook' }))

    await waitFor(() => expect(sent[0]?.body).toEqual({ enabled: false }))
  })

  test('a refused switch says why above the list', async () => {
    withSources([payments])
    server.use(respond(updateSource, 'patch', getUpdateSourceUrl(payments.id), 403, { detail: 'No' }))
    const rendered = open()

    await rendered.user.click(await screen.findByRole('switch', { name: 'Accept events from Payments webhook' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Couldn't turn off Payments webhook. Only members and leads can change sources.",
    )
  })
})

describe('DELETE /sources/{id}', () => {
  test('asks, deletes and confirms with a toast', async () => {
    withSources([payments])
    server.use(respond(deleteSource, 'delete', getDeleteSourceUrl(payments.id), 204, undefined))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Delete source')
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete Payments webhook?' })
    withSources([])
    await rendered.user.click(within(confirm).getByRole('button', { name: 'Delete source' }))

    expect(await screen.findByText('Payments webhook deleted')).toBeInTheDocument()
    expect(await screen.findByText('No sources yet')).toBeInTheDocument()
  })

  test.each([
    [403, 'Only members and leads can delete sources.'],
    [404, 'This source no longer exists.'],
  ] as const)('%i keeps the dialog open with the reason', async (status, message) => {
    withSources([payments])
    server.use(respond(deleteSource, 'delete', getDeleteSourceUrl(payments.id), status, { detail: 'x' }))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Delete source')
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete Payments webhook?' })
    await rendered.user.click(within(confirm).getByRole('button', { name: 'Delete source' }))

    expect(await within(confirm).findByRole('alert')).toHaveTextContent(message)
  })

  test('the 501 stub shows the shared fallback', async () => {
    withSources([payments])
    server.use(http.delete(getDeleteSourceUrl(payments.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Delete source')
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete Payments webhook?' })
    await rendered.user.click(within(confirm).getByRole('button', { name: 'Delete source' }))

    expect(await within(confirm).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('POST /sources/{id}/token', () => {
  test('asks first, shows the new token once with a curl example, and forgets it on close', async () => {
    withSources([payments])
    server.use(respond(rotateSourceToken, 'post', getRotateSourceTokenUrl(payments.id), 200, { token: TOKEN }))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Rotate token')
    const confirm = await screen.findByRole('alertdialog', { name: 'Rotate the token for Payments webhook?' })
    expect(confirm).toHaveTextContent('The current token stops working at once.')
    await rendered.user.click(within(confirm).getByRole('button', { name: 'Rotate token' }))

    const reveal = await screen.findByRole('dialog', { name: 'New token for Payments webhook' })
    expect(within(reveal).getByText('This token is shown only once.')).toBeInTheDocument()
    expect(within(reveal).getByLabelText('Ingest token')).toHaveValue(TOKEN)
    expect(within(reveal).getByLabelText('Send a test event')).toHaveTextContent(`Authorization: Bearer ${TOKEN}`)
    await rendered.user.click(within(reveal).getByRole('button', { name: 'Copy token' }))
    expect(await navigator.clipboard.readText()).toBe(TOKEN)

    // The token stays out of storage and the query cache.
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(TOKEN)
    expect(JSON.stringify(rendered.queryClient.getMutationCache().getAll().map((m) => m.state.data))).not.toContain(TOKEN)

    await rendered.user.click(within(reveal).getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.queryByText(TOKEN)).not.toBeInTheDocument()

    await rowAction(rendered, 'Payments webhook', 'Rotate token')
    expect(await screen.findByRole('alertdialog', { name: 'Rotate the token for Payments webhook?' })).toBeInTheDocument()
    expect(screen.queryByDisplayValue(TOKEN)).not.toBeInTheDocument()
  })

  test('Create token on a source without one shows the token once and refreshes has_token', async () => {
    const ledger = source('ledger-ws', 'Ledger stream', { type: 'websocket', ingest_url: '/ingest/ledger-ws/ws', has_token: false })
    withSources([ledger])
    server.use(respond(rotateSourceToken, 'post', getRotateSourceTokenUrl(ledger.id), 200, { token: TOKEN }))
    const rendered = open()

    const row = await screen.findByRole('row', { name: /Ledger stream/ })
    await rendered.user.click(within(row).getByRole('button', { name: 'Create token for Ledger stream' }))
    const dialog = await screen.findByRole('dialog', { name: 'Token for Ledger stream' })
    expect(dialog).toHaveTextContent('Producers need an ingest token to send events to it.')
    withSources([{ ...ledger, has_token: true }])
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Create token' }))

    expect(await within(dialog).findByText('This token is shown only once.')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Send a test event')).toHaveTextContent(
      `websocat -H 'Authorization: Bearer ${TOKEN}' '${window.location.origin.replace(/^http/, 'ws')}/ingest/ledger-ws/ws'`,
    )
    expect(JSON.stringify(rendered.queryClient.getQueryCache().getAll().map((q) => q.state.data))).not.toContain(TOKEN)

    await rendered.user.click(within(dialog).getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(screen.getByRole('row', { name: /Ledger stream/ })).not.toHaveTextContent('No token yet'))
    expect(screen.getByRole('row', { name: /Ledger stream/ })).toHaveTextContent('Set')
    await rowAction(rendered, 'Ledger stream', 'Rotate token')
    expect(await screen.findByRole('alertdialog', { name: 'Rotate the token for Ledger stream?' })).toBeInTheDocument()
  })

  test.each([
    [403, 'Only members and leads can change ingest tokens.'],
    [404, 'This source no longer exists.'],
  ] as const)('%i shows the reason in the confirmation', async (status, message) => {
    withSources([payments])
    server.use(respond(rotateSourceToken, 'post', getRotateSourceTokenUrl(payments.id), status, { detail: 'x' }))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Rotate token')
    const confirm = await screen.findByRole('alertdialog', { name: 'Rotate the token for Payments webhook?' })
    await rendered.user.click(within(confirm).getByRole('button', { name: 'Rotate token' }))

    expect(await within(confirm).findByRole('alert')).toHaveTextContent(message)
  })

  test('the 501 stub shows the shared fallback', async () => {
    withSources([payments])
    server.use(
      http.post(getRotateSourceTokenUrl(payments.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Rotate token')
    const confirm = await screen.findByRole('alertdialog', { name: 'Rotate the token for Payments webhook?' })
    await rendered.user.click(within(confirm).getByRole('button', { name: 'Rotate token' }))

    expect(await within(confirm).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
