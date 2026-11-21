import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { getListEventSchemasUrl, listEventSchemas } from '@/api/generated/event-schemas/event-schemas'
import type { EventSchemaRead, SourceRead } from '@/api/generated/model'
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
import { eventSchema, source } from '@/test/sources'
import { openAs, petraIn, recordRequests, settlements } from '@/test/teams'

const PATH = '/teams/settlements/sources'
const lead = petraIn('lead')
const paymentFailed = eventSchema('payment-failed', 2)
const refundFailed = eventSchema('refund-failed', 1)
const payments = source('payments-webhook', 'Payments webhook')
const TOKEN = 'pc_live_9f8e7d6c5b4a'

function withSources(sources: SourceRead[]) {
  server.use(respond(listSources, 'get', getListSourcesUrl(), 200, sources))
}

function withSchemas(schemas: EventSchemaRead[] = [paymentFailed, refundFailed]) {
  server.use(respond(listEventSchemas, 'get', getListEventSchemasUrl(), 200, schemas))
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

/** Fills name and the fixed schema of the New source dialog. */
async function fillFixed(rendered: Rendered, dialog: HTMLElement, name = 'Payments webhook') {
  await rendered.user.type(within(dialog).getByLabelText('Name'), name)
  await pick(rendered, within(dialog).getByRole('combobox', { name: 'Schema' }), 'payment-failed v2')
}

describe('GET /sources', () => {
  test('lists name, slug, type, schema, ingest URL and the enabled switch', async () => {
    const byType = source('ledger-ws', 'Ledger stream', {
      type: 'websocket',
      enabled: false,
      schema_resolution: {
        mode: 'discriminator',
        field: 'type',
        mapping: { payment: paymentFailed.id, refund: refundFailed.id },
      },
    })
    withSources([payments, byType])
    withSchemas()
    open()

    await screen.findByText('Ledger stream')
    const rows = within(screen.getByRole('table', { name: 'Sources' })).getAllByRole('row').slice(1)
    await waitFor(() => expect(rows[0]).toHaveTextContent('payment-failed v2'))
    expect(rows[0]).toHaveTextContent('Payments webhookpayments-webhookWebhookpayment-failed v2/ingest/payments-webhook')
    expect(rows[1]).toHaveTextContent('Ledger streamledger-wsWebSocketBy type, 2 schemas/ingest/ledger-ws')
    expect(screen.getByRole('switch', { name: 'Accept events from Payments webhook' })).toBeChecked()
    expect(screen.getByRole('switch', { name: 'Accept events from Ledger stream' })).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Actions for Ledger stream' })).toBeInTheDocument()
  })

  test('copies the ingest URL', async () => {
    withSources([payments])
    withSchemas()
    const rendered = open()

    await rendered.user.click(await screen.findByRole('button', { name: 'Copy ingest URL of Payments webhook' }))

    expect(await navigator.clipboard.readText()).toBe('/ingest/payments-webhook')
    expect(screen.getByText('Copied')).toBeInTheDocument()
  })

  test('shows skeleton rows while loading', async () => {
    server.use(http.get(getListSourcesUrl(), () => delay('infinite')))
    withSchemas()
    open()

    expect(await screen.findAllByTestId('skeleton-row')).toHaveLength(5)
  })

  test('shows an empty state when the team has no sources', async () => {
    withSources([])
    withSchemas()
    open()

    expect(await screen.findByText('No sources yet')).toBeInTheDocument()
  })

  test('422 shows the error state', async () => {
    server.use(respond(listSources, 'get', getListSourcesUrl(), 422, { detail: [] }))
    withSchemas()
    open()

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load sources")
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.get(getListSourcesUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    withSchemas()
    open()

    expect(await screen.findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('a viewer sees the list read-only', async () => {
    withSources([payments])
    withSchemas()
    open('viewer')

    await screen.findByText('Payments webhook')
    expect(within(screen.getByRole('table', { name: 'Sources' })).getAllByRole('row')[1]).toHaveTextContent('On')
    expect(screen.getByText('Only members and leads can change this.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New source' })).not.toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Actions for/ })).not.toBeInTheDocument()
  })

  test('a member gets the same controls as a lead', async () => {
    withSources([payments])
    withSchemas()
    open('member')

    expect(await screen.findByRole('button', { name: 'New source' })).toBeInTheDocument()
    expect(await screen.findByRole('switch', { name: 'Accept events from Payments webhook' })).toBeInTheDocument()
  })
})

describe('POST /sources', () => {
  test('derives the slug from the name, creates a fixed-schema source, then shows its first token once', async () => {
    withSources([])
    withSchemas()
    const created = source('payments-webhook', 'Payments webhook', { schema_resolution: { mode: 'fixed', schema_id: paymentFailed.id } })
    server.use(
      respond(createSource, 'post', getCreateSourceUrl(), 201, created),
      respond(rotateSourceToken, 'post', getRotateSourceTokenUrl(created.id), 200, { token: TOKEN }),
    )
    const sent = recordRequests('post', getCreateSourceUrl())
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillFixed(rendered, dialog)
    expect(within(dialog).getByLabelText('Slug')).toHaveValue('payments-webhook')
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    await waitFor(() =>
      expect(sent[0]?.body).toEqual({
        name: 'Payments webhook',
        slug: 'payments-webhook',
        type: 'webhook',
        team_id: settlements.id,
        schema_resolution: { mode: 'fixed', schema_id: paymentFailed.id },
        severity: { field: null, values: {}, default: 'info' },
        enabled: true,
      }),
    )
    const step = await screen.findByRole('dialog', { name: 'Payments webhook added' })
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
  })

  test('sends a discriminator mapping and a severity mapping', async () => {
    withSources([])
    withSchemas()
    server.use(respond(createSource, 'post', getCreateSourceUrl(), 201, payments))
    const sent = recordRequests('post', getCreateSourceUrl())
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await rendered.user.type(within(dialog).getByLabelText('Name'), 'Ledger')
    await pick(rendered, within(dialog).getByRole('combobox', { name: 'Type' }), 'WebSocket')
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Picked by a field' }))
    await rendered.user.type(within(dialog).getByLabelText('Field'), 'kind')
    const [addSchemaValue, addSeverityValue] = within(dialog).getAllByRole('button', { name: 'Add value' })
    if (addSchemaValue === undefined || addSeverityValue === undefined) throw new Error('no Add value buttons')
    await rendered.user.click(addSchemaValue)
    await rendered.user.type(within(dialog).getByLabelText('Value 1'), 'payment')
    await pick(rendered, within(dialog).getByRole('combobox', { name: 'Schema for value 1' }), 'payment-failed v2')
    await rendered.user.type(within(dialog).getByLabelText('Severity field'), 'level')
    await rendered.user.click(addSeverityValue)
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
        schema_resolution: { mode: 'discriminator', field: 'kind', mapping: { payment: paymentFailed.id } },
        severity: { field: 'level', values: { FATAL: 'critical' }, default: 'info' },
        enabled: false,
      }),
    )
  })

  test('checks the form before sending: a schema, at least one mapping value, no repeated values', async () => {
    withSources([])
    withSchemas()
    const rendered = open()
    const dialog = await openNewSource(rendered)
    await rendered.user.type(within(dialog).getByLabelText('Name'), 'Ledger')

    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))
    expect(await within(dialog).findByText('Pick a schema.')).toBeInTheDocument()

    await rendered.user.click(within(dialog).getByRole('button', { name: 'Picked by a field' }))
    await rendered.user.type(within(dialog).getByLabelText('Field'), 'kind')
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))
    expect(await within(dialog).findByText('Add at least one value and its schema.')).toBeInTheDocument()

    const [addSchemaValue] = within(dialog).getAllByRole('button', { name: 'Add value' })
    if (addSchemaValue === undefined) throw new Error('no Add value button')
    await rendered.user.click(addSchemaValue)
    await rendered.user.click(addSchemaValue)
    await rendered.user.type(within(dialog).getByLabelText('Value 1'), 'payment')
    await rendered.user.type(within(dialog).getByLabelText('Value 2'), 'payment')
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))
    expect(await within(dialog).findByText('This value is already in the list.')).toBeInTheDocument()
  })

  test('409 shows the duplicate slug under Slug', async () => {
    withSources([])
    withSchemas()
    server.use(respond(createSource, 'post', getCreateSourceUrl(), 409, { detail: 'Slug taken' }))
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillFixed(rendered, dialog)
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    await waitFor(() => expect(fieldError(dialog, 'Slug')).toHaveTextContent('Another source already uses this slug.'))
  })

  test('422 puts each error under its field, including a tagged-union path', async () => {
    withSources([])
    withSchemas()
    server.use(
      respond(createSource, 'post', getCreateSourceUrl(), 422, {
        detail: [
          { loc: ['body', 'name'], msg: 'Name is reserved', type: 'value_error' },
          { loc: ['body', 'schema_resolution', 'fixed', 'schema_id'], msg: 'Unknown schema', type: 'value_error' },
        ],
      }),
    )
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillFixed(rendered, dialog)
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    await waitFor(() => expect(fieldError(dialog, 'Name')).toHaveTextContent('Name is reserved'))
    expect(fieldError(dialog, 'Schema')).toHaveTextContent('Unknown schema')
  })

  test.each([
    [400, "Couldn't save the source. Reload the page and try again."],
    [403, 'Only members and leads can add sources.'],
    [404, 'The team or a picked schema no longer exists.'],
  ] as const)('%i shows a form error', async (status, message) => {
    withSources([])
    withSchemas()
    server.use(respond(createSource, 'post', getCreateSourceUrl(), status, { detail: 'x' }))
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillFixed(rendered, dialog)
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(message)
  })

  test('the 501 stub shows the shared fallback in the dialog', async () => {
    withSources([])
    withSchemas()
    server.use(http.post(getCreateSourceUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const rendered = open()
    const dialog = await openNewSource(rendered)

    await fillFixed(rendered, dialog)
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Add source' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('a team without schemas gets a link to add one', async () => {
    withSources([])
    withSchemas([])
    const rendered = open()
    const dialog = await openNewSource(rendered)

    expect(await within(dialog).findByRole('link', { name: 'Add a schema' })).toHaveAttribute(
      'href',
      '/teams/settlements/schemas/new',
    )
  })
})

describe('GET and PATCH /sources/{id}', () => {
  test('Edit source loads the source and sends only the changed name', async () => {
    withSources([payments])
    withSchemas()
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
    withSchemas()
    server.use(respond(getSource, 'get', getGetSourceUrl(payments.id), 404, { detail: 'Not found' }))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Edit source')

    const dialog = await screen.findByRole('dialog', { name: 'Edit source' })
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This source no longer exists.')
  })

  test('GET 501 shows the shared fallback', async () => {
    withSources([payments])
    withSchemas()
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
    withSchemas()
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
    withSchemas()
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
    withSchemas()
    server.use(respond(updateSource, 'patch', getUpdateSourceUrl(payments.id), 200, { ...payments, enabled: false }))
    const sent = recordRequests('patch', getUpdateSourceUrl(payments.id))
    const rendered = open()

    await rendered.user.click(await screen.findByRole('switch', { name: 'Accept events from Payments webhook' }))

    await waitFor(() => expect(sent[0]?.body).toEqual({ enabled: false }))
  })

  test('a refused switch says why above the list', async () => {
    withSources([payments])
    withSchemas()
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
    withSchemas()
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
    withSchemas()
    server.use(respond(deleteSource, 'delete', getDeleteSourceUrl(payments.id), status, { detail: 'x' }))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Delete source')
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete Payments webhook?' })
    await rendered.user.click(within(confirm).getByRole('button', { name: 'Delete source' }))

    expect(await within(confirm).findByRole('alert')).toHaveTextContent(message)
  })

  test('the 501 stub shows the shared fallback', async () => {
    withSources([payments])
    withSchemas()
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
    withSchemas()
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

  test.each([
    [403, 'Only members and leads can change ingest tokens.'],
    [404, 'This source no longer exists.'],
  ] as const)('%i shows the reason in the confirmation', async (status, message) => {
    withSources([payments])
    withSchemas()
    server.use(respond(rotateSourceToken, 'post', getRotateSourceTokenUrl(payments.id), status, { detail: 'x' }))
    const rendered = open()

    await rowAction(rendered, 'Payments webhook', 'Rotate token')
    const confirm = await screen.findByRole('alertdialog', { name: 'Rotate the token for Payments webhook?' })
    await rendered.user.click(within(confirm).getByRole('button', { name: 'Rotate token' }))

    expect(await within(confirm).findByRole('alert')).toHaveTextContent(message)
  })

  test('the 501 stub shows the shared fallback', async () => {
    withSources([payments])
    withSchemas()
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
