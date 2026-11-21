import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import {
  createEventSchema,
  getCreateEventSchemaUrl,
  getEventSchema,
  getGetEventSchemaUrl,
  getListEventSchemasUrl,
  getValidateEventUrl,
  listEventSchemas,
  validateEvent,
} from '@/api/generated/event-schemas/event-schemas'
import type { EventSchemaRead } from '@/api/generated/model'
import { respond } from '@/test/http'
import { server } from '@/test/server'
import { eventSchema } from '@/test/sources'
import { openAs, petraIn, recordRequests, settlements } from '@/test/teams'

const LIST = '/teams/settlements/schemas'
const lead = petraIn('lead')
const v1 = eventSchema('payment-failed', 1)
const v2 = eventSchema('payment-failed', 2, {
  description: 'A settlement payment failed',
  json_schema: {
    type: 'object',
    $defs: { money: { type: 'object', properties: { currency: { type: 'string', maxLength: 3 } } } },
    properties: {
      workflowId: { type: 'string' },
      error: { type: 'object', properties: { code: { enum: ['TIMEOUT', 'REJECTED'] } }, required: ['code'] },
      amount: { $ref: '#/$defs/money' },
    },
    required: ['workflowId'],
  },
})
const refund = eventSchema('refund-failed', 1)

function withList(schemas: EventSchemaRead[]) {
  server.use(respond(listEventSchemas, 'get', getListEventSchemasUrl(), 200, schemas))
}

function withSchema(schema: EventSchemaRead) {
  server.use(respond(getEventSchema, 'get', getGetEventSchemaUrl(schema.id), 200, schema))
}

/** Replaces the whole text of a textarea; `user.type` would read `{` as a key descriptor. */
function setText(element: HTMLElement, value: string) {
  fireEvent.change(element, { target: { value } })
}

/** Switches the new-schema editor from the builder to the JSON text. */
async function editAsJson(user: ReturnType<typeof openAs>['user']) {
  await user.click(await screen.findByRole('button', { name: 'JSON' }))
}

/** The error text under the field labelled `label`. */
function fieldError(label: string) {
  const field = screen.getByText(label, { selector: 'label' }).closest('[data-slot="field"]')
  if (!(field instanceof HTMLElement)) throw new Error(`no field labelled ${label}`)
  return within(field).getByText((_, element) => element?.getAttribute('data-slot') === 'field-error')
}

describe('GET /event-schemas', () => {
  test('groups versions by name, newest first, each linking to its page', async () => {
    withList([v1, refund, v2])
    openAs(lead, LIST)

    const table = await screen.findByRole('table', { name: 'Event schemas' })
    await within(table).findByRole('link', { name: 'payment-failed' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((row) => row.textContent)).toEqual([
      'payment-failedv2v1A settlement payment failed',
      'refund-failedv1',
    ])
    expect(within(table).getByRole('link', { name: 'payment-failed' })).toHaveAttribute('href', `${LIST}/${v2.id}`)
    expect(within(table).getByRole('link', { name: 'payment-failed version 1' })).toHaveAttribute('href', `${LIST}/${v1.id}`)
    expect(screen.getByRole('link', { name: 'New schema' })).toHaveAttribute('href', `${LIST}/new`)
  })

  test('shows skeleton rows while loading', async () => {
    server.use(http.get(getListEventSchemasUrl(), () => delay('infinite')))
    openAs(lead, LIST)

    expect(await screen.findAllByTestId('skeleton-row')).toHaveLength(5)
  })

  test('shows an empty state', async () => {
    withList([])
    openAs(lead, LIST)

    expect(await screen.findByText('No event schemas yet')).toBeInTheDocument()
  })

  test('422 shows the error state', async () => {
    server.use(respond(listEventSchemas, 'get', getListEventSchemasUrl(), 422, { detail: [] }))
    openAs(lead, LIST)

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load event schemas")
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.get(getListEventSchemasUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    openAs(lead, LIST)

    expect(await screen.findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('a viewer reads the list without New schema', async () => {
    withList([v1])
    openAs(petraIn('viewer'), LIST)

    expect(await screen.findByRole('link', { name: 'payment-failed' })).toBeInTheDocument()
    expect(screen.getByText('Only members and leads can change this.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'New schema' })).not.toBeInTheDocument()
  })
})

describe('GET /event-schemas/{id}', () => {
  test('shows the field tree, the JSON Schema and the versions', async () => {
    withSchema(v2)
    withList([v2, v1])
    openAs(lead, `${LIST}/${v2.id}`)

    expect(await screen.findByRole('heading', { level: 1, name: 'payment-failed v2' })).toBeInTheDocument()
    const fields = screen.getByRole('list', { name: 'Fields' })
    expect(fields).toHaveTextContent('workflowIdstringrequired')
    expect(within(fields).getByRole('list', { name: 'Fields of error' })).toHaveTextContent('coderequiredone of "TIMEOUT", "REJECTED"')
    expect(within(fields).getByRole('list', { name: 'Fields of amount' })).toHaveTextContent('currencystringat most 3 characters')
    expect(screen.getByLabelText('JSON Schema')).toHaveTextContent('"workflowId"')
    const versions = await screen.findByRole('navigation', { name: 'Versions' })
    expect(within(versions).getByRole('link', { name: 'v2' })).toHaveAttribute('aria-current', 'page')
    expect(within(versions).getByRole('link', { name: 'v1' })).toHaveAttribute('href', `${LIST}/${v1.id}`)
    expect(screen.getByRole('link', { name: 'New version' })).toHaveAttribute('href', `${LIST}/new?from=${v2.id}`)
  })

  test('a viewer gets no New version', async () => {
    withSchema(v2)
    withList([v2])
    openAs(petraIn('viewer'), `${LIST}/${v2.id}`)

    expect(await screen.findByRole('heading', { level: 1, name: 'payment-failed v2' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'New version' })).not.toBeInTheDocument()
  })

  test("another team's schema is readable, without New version", async () => {
    const foreign = eventSchema('ledger-entry', 1, { team_id: 'team-ledger' })
    withSchema(foreign)
    withList([foreign])
    openAs(lead, `${LIST}/${foreign.id}`)

    expect(await screen.findByText('Another team owns this schema. Rules in any team can use it.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'New version' })).not.toBeInTheDocument()
  })

  test('404 says the schema does not exist', async () => {
    server.use(respond(getEventSchema, 'get', getGetEventSchemaUrl('missing'), 404, { detail: 'Not found' }))
    openAs(lead, `${LIST}/missing`)

    expect(await screen.findByRole('alert')).toHaveTextContent("This schema doesn't exist")
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.get(getGetEventSchemaUrl(v2.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    openAs(lead, `${LIST}/${v2.id}`)

    expect(await screen.findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('POST /event-schemas/{id}/validate', () => {
  async function openSample() {
    withSchema(v2)
    withList([v2])
    const rendered = openAs(lead, `${LIST}/${v2.id}`)
    const sample = await screen.findByLabelText('Sample event')
    return { ...rendered, sample }
  }

  test('a valid sample says it matches, and the payload is sent as JSON', async () => {
    server.use(respond(validateEvent, 'post', getValidateEventUrl(v2.id), 200, { valid: true, issues: [] }))
    const sent = recordRequests('post', getValidateEventUrl(v2.id))
    const { user, sample } = await openSample()

    setText(sample, '{"workflowId": "wf-8f21"}')
    await user.click(screen.getByRole('button', { name: 'Check sample' }))

    expect(await screen.findByText('The sample matches the schema.')).toBeInTheDocument()
    await waitFor(() => expect(sent[0]?.body).toEqual({ payload: { workflowId: 'wf-8f21' } }))
  })

  test('an invalid sample lists each problem with its path', async () => {
    server.use(
      respond(validateEvent, 'post', getValidateEventUrl(v2.id), 200, {
        valid: false,
        issues: [
          { path: '', message: "'workflowId' is a required property" },
          { path: '/amount/currency', message: "'EURO' is too long" },
        ],
      }),
    )
    const { user, sample } = await openSample()

    setText(sample, '{"amount": {"currency": "EURO"}}')
    await user.click(screen.getByRole('button', { name: 'Check sample' }))

    expect(await screen.findByText("The sample doesn't match the schema.")).toBeInTheDocument()
    const problems = screen.getByRole('list', { name: 'Problems' })
    expect(within(problems).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      "/'workflowId' is a required property",
      "/amount/currency'EURO' is too long",
    ])
  })

  test('broken JSON shows the line and column inline and sends nothing', async () => {
    const { user, sample } = await openSample()

    setText(sample, '{\n  "a": 1,\n}')
    await user.click(screen.getByRole('button', { name: 'Check sample' }))

    expect(fieldError('Sample event')).toHaveTextContent(/^Line 3, column 1: /)
  })

  test('a JSON array is refused before sending', async () => {
    const { user, sample } = await openSample()

    setText(sample, '[1]')
    await user.click(screen.getByRole('button', { name: 'Check sample' }))

    expect(fieldError('Sample event')).toHaveTextContent('An event payload is a JSON object')
  })

  test.each([
    [400, "Couldn't read the sample."],
    [404, 'This schema no longer exists.'],
  ] as const)('%i says why the check did not run', async (status, message) => {
    server.use(respond(validateEvent, 'post', getValidateEventUrl(v2.id), status, { detail: 'x' }))
    const { user, sample } = await openSample()

    setText(sample, '{}')
    await user.click(screen.getByRole('button', { name: 'Check sample' }))

    expect(await screen.findByText(new RegExp(message.replace('.', '\\.')))).toBeInTheDocument()
  })

  test('422 shows the validation message', async () => {
    server.use(
      respond(validateEvent, 'post', getValidateEventUrl(v2.id), 422, {
        detail: [{ loc: ['body', 'payload'], msg: 'Payload too large', type: 'value_error' }],
      }),
    )
    const { user, sample } = await openSample()

    setText(sample, '{}')
    await user.click(screen.getByRole('button', { name: 'Check sample' }))

    expect(await screen.findByText('Payload too large')).toBeInTheDocument()
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.post(getValidateEventUrl(v2.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const { user, sample } = await openSample()

    setText(sample, '{}')
    await user.click(screen.getByRole('button', { name: 'Check sample' }))

    expect(await screen.findByText("This feature isn't available yet.")).toBeInTheDocument()
  })
})

describe('POST /event-schemas', () => {
  test('a new name starts at version 1 with a field preview, then opens the saved schema', async () => {
    const saved = eventSchema('card-declined', 1)
    server.use(respond(createEventSchema, 'post', getCreateEventSchemaUrl(), 201, saved))
    withSchema(saved)
    withList([saved])
    const sent = recordRequests('post', getCreateEventSchemaUrl())
    const { user, router } = openAs(lead, `${LIST}/new`)
    await editAsJson(user)

    const preview = await screen.findByRole('list', { name: 'Fields' })
    expect(preview).toHaveTextContent('messagestringrequiredat most 500 characters')
    await user.type(screen.getByLabelText('Name'), 'card-declined')
    setText(screen.getByLabelText('JSON Schema'), '{"type": "object", "properties": {"workflowId": {"type": "string"}}}')
    expect(screen.getByRole('list', { name: 'Fields' })).toHaveTextContent('workflowIdstring')
    await user.click(screen.getByRole('button', { name: 'Save schema' }))

    await waitFor(() =>
      expect(sent[0]?.body).toEqual({
        name: 'card-declined',
        version: 1,
        team_id: settlements.id,
        description: null,
        json_schema: { type: 'object', properties: { workflowId: { type: 'string' } } },
      }),
    )
    await waitFor(() => expect(router.state.location.pathname).toBe(`${LIST}/${saved.id}`))
    expect(await screen.findByText('card-declined v1 saved')).toBeInTheDocument()
  })

  test('broken JSON shows the line and column while typing and blocks saving', async () => {
    const { user } = openAs(lead, `${LIST}/new`)
    await editAsJson(user)
    const editor = await screen.findByLabelText('JSON Schema')

    await user.type(screen.getByLabelText('Name'), 'card-declined')
    setText(editor, '{\n  "type": "object",\n  "properties": }')

    expect(fieldError('JSON Schema')).toHaveTextContent(/^Line 3, column 17: /)
    expect(screen.getByText('Fix the JSON to see the fields.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save schema' }))
    expect(fieldError('JSON Schema')).toHaveTextContent(/^Line 3/)
  })

  test('409 for a new name points to adding a version', async () => {
    server.use(respond(createEventSchema, 'post', getCreateEventSchemaUrl(), 409, { detail: 'Exists' }))
    const { user } = openAs(lead, `${LIST}/new`)

    await user.type(await screen.findByLabelText('Name'), 'payment-failed')
    await user.click(screen.getByRole('button', { name: 'Save schema' }))

    await waitFor(() => expect(fieldError('Name')).toHaveTextContent('A schema with this name already exists.'))
  })

  test('422 on json_schema shows under the editor', async () => {
    server.use(
      respond(createEventSchema, 'post', getCreateEventSchemaUrl(), 422, {
        detail: [{ loc: ['body', 'json_schema'], msg: "'strin' is not valid under any of the given schemas", type: 'value_error' }],
      }),
    )
    const { user } = openAs(lead, `${LIST}/new`)
    await editAsJson(user)

    await user.type(await screen.findByLabelText('Name'), 'card-declined')
    await user.click(screen.getByRole('button', { name: 'Save schema' }))

    await waitFor(() => expect(fieldError('JSON Schema')).toHaveTextContent("'strin' is not valid"))
  })

  test('422 on json_schema shows under the builder', async () => {
    server.use(
      respond(createEventSchema, 'post', getCreateEventSchemaUrl(), 422, {
        detail: [{ loc: ['body', 'json_schema'], msg: "'strin' is not valid under any of the given schemas", type: 'value_error' }],
      }),
    )
    const { user } = openAs(lead, `${LIST}/new`)

    await user.type(await screen.findByLabelText('Name'), 'card-declined')
    await user.click(screen.getByRole('button', { name: 'Save schema' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("'strin' is not valid")
  })

  test.each([
    [400, "Couldn't read the schema."],
    [403, 'Only members and leads can add event schemas.'],
  ] as const)('%i shows a form error', async (status, message) => {
    server.use(respond(createEventSchema, 'post', getCreateEventSchemaUrl(), status, { detail: 'x' }))
    const { user } = openAs(lead, `${LIST}/new`)

    await user.type(await screen.findByLabelText('Name'), 'card-declined')
    await user.click(screen.getByRole('button', { name: 'Save schema' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.post(getCreateEventSchemaUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const { user } = openAs(lead, `${LIST}/new`)

    await user.type(await screen.findByLabelText('Name'), 'card-declined')
    await user.click(screen.getByRole('button', { name: 'Save schema' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('New version keeps the name, takes the next number and starts from the old JSON', async () => {
    const v3 = eventSchema('payment-failed', 3)
    withSchema(v1)
    withList([v2, v1])
    server.use(respond(createEventSchema, 'post', getCreateEventSchemaUrl(), 201, v3))
    withSchema(v3)
    const sent = recordRequests('post', getCreateEventSchemaUrl())
    const { user } = openAs(lead, `${LIST}/new?from=${v1.id}`)

    expect(await screen.findByRole('heading', { level: 1, name: 'New version of payment-failed' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Name of workflowId')).toHaveValue('workflowId')
    await editAsJson(user)
    expect(screen.getByLabelText('JSON Schema')).toHaveValue(`${JSON.stringify(v1.json_schema, null, 2)}\n`)
    await user.click(screen.getByRole('button', { name: 'Save version' }))

    await waitFor(() =>
      expect(sent[0]?.body).toMatchObject({ name: 'payment-failed', version: 3, team_id: settlements.id, json_schema: v1.json_schema }),
    )
  })

  test('409 on a new version says someone saved it meanwhile', async () => {
    withSchema(v2)
    withList([v2, v1])
    server.use(respond(createEventSchema, 'post', getCreateEventSchemaUrl(), 409, { detail: 'Exists' }))
    const { user } = openAs(lead, `${LIST}/new?from=${v2.id}`)

    await user.click(await screen.findByRole('button', { name: 'Save version' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Version 3 already exists; someone saved it meanwhile.')
  })
})

describe('schema builder', () => {
  test('builds nested, optional, fixed-value and constrained fields from the palette and sends the JSON Schema', async () => {
    const saved = eventSchema('card-declined', 1)
    server.use(respond(createEventSchema, 'post', getCreateEventSchemaUrl(), 201, saved))
    withSchema(saved)
    withList([saved])
    const sent = recordRequests('post', getCreateEventSchemaUrl())
    const { user } = openAs(lead, `${LIST}/new`)

    await user.type(await screen.findByLabelText('Name'), 'card-declined')
    expect(screen.getByLabelText('Name of message')).toHaveValue('message')
    await user.click(screen.getByRole('switch', { name: 'message is required' }))

    await user.click(screen.getByRole('button', { name: 'Add object field' }))
    const objectName = screen.getByLabelText('Name of field')
    expect(objectName).toHaveFocus()
    await user.clear(objectName)
    await user.type(objectName, 'error')
    await user.click(screen.getByRole('button', { name: 'Add field to error' }))
    const codeName = screen.getByLabelText('Name of error.field')
    await user.clear(codeName)
    await user.type(codeName, 'code')
    await user.click(screen.getByRole('combobox', { name: 'Type of error.code' }))
    await user.click(await screen.findByRole('option', { name: 'Fixed values' }))
    await user.type(screen.getByLabelText('Value 1 of error.code'), 'TIMEOUT')
    await user.click(screen.getByRole('button', { name: 'Add value to error.code' }))
    await user.type(screen.getByLabelText('Value 2 of error.code'), 'REJECTED')

    await user.click(screen.getByRole('button', { name: 'Constraints of message' }))
    await user.clear(screen.getByLabelText('Max length of message'))
    await user.type(screen.getByLabelText('Max length of message'), '200')
    await user.click(screen.getByRole('switch', { name: 'message can be null' }))

    expect(screen.getByLabelText('Generated JSON Schema')).toHaveTextContent('"REJECTED"')
    await user.click(screen.getByRole('button', { name: 'Save schema' }))

    await waitFor(() =>
      expect(sent[0]?.body).toMatchObject({
        json_schema: {
          $schema: 'https://json-schema.org/draft/2020-12/schema',
          type: 'object',
          properties: {
            message: { type: ['string', 'null'], maxLength: 200 },
            error: { type: 'object', properties: { code: { enum: ['TIMEOUT', 'REJECTED'] } }, required: ['code'] },
          },
          required: ['error'],
        },
      }),
    )
  })

  test('moves fields with the actions menu: into the object above, out again, and up', async () => {
    const { user } = openAs(lead, `${LIST}/new`)
    await user.click(await screen.findByRole('button', { name: 'Add object field' }))
    await user.click(screen.getByRole('button', { name: 'Add text field' }))
    const fields = () => within(screen.getByRole('list', { name: 'Fields' }))

    await user.click(screen.getByRole('button', { name: 'Actions for field_2' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Move into field' }))
    expect(screen.getByLabelText('Name of field.field_2')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Actions for field.field_2' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Move out of field' }))
    expect(screen.getByLabelText('Name of field_2')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Actions for field_2' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Move up' }))
    expect(fields().getAllByLabelText(/^Name of /).map((input) => (input as HTMLInputElement).value)).toEqual(['message', 'field_2', 'field'])
  })

  test('problems show under the field and block saving; the JSON keeps its last valid version', async () => {
    const { user } = openAs(lead, `${LIST}/new`)

    await user.type(await screen.findByLabelText('Name'), 'card-declined')
    await user.clear(screen.getByLabelText('Name of message'))
    await user.click(screen.getByRole('button', { name: 'Constraints of unnamed field' }))
    await user.type(screen.getByLabelText('Min length of unnamed field'), '600')

    expect(screen.getByText('Enter a field name.')).toBeInTheDocument()
    expect(screen.getByText('Use a maximum length at least as large as the minimum.')).toBeInTheDocument()
    expect(screen.getByLabelText('Generated JSON Schema')).toHaveTextContent('"message"')
    await user.click(screen.getByRole('button', { name: 'Save schema' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Fix the fields marked in red, then save.')
  })

  test('switching to JSON and back keeps the builder as it was, problems included', async () => {
    const { user } = openAs(lead, `${LIST}/new`)
    await user.click(await screen.findByRole('button', { name: 'Constraints of message' }))
    await user.type(screen.getByLabelText('Min length of message'), '600')
    expect(screen.getByText('Use a maximum length at least as large as the minimum.')).toBeInTheDocument()

    await editAsJson(user)
    await user.click(screen.getByRole('button', { name: 'Builder' }))
    await user.click(screen.getByRole('button', { name: 'Constraints of message' }))

    expect(screen.getByLabelText('Min length of message')).toHaveValue('600')
    expect(screen.getByText('Use a maximum length at least as large as the minimum.')).toBeInTheDocument()
  })

  test('a schema with $ref opens as JSON, and the builder says what it cannot show', async () => {
    withSchema(v2)
    withList([v2, v1])
    const { user } = openAs(lead, `${LIST}/new?from=${v2.id}`)

    expect(await screen.findByLabelText('JSON Schema')).toHaveValue(`${JSON.stringify(v2.json_schema, null, 2)}\n`)
    await user.click(screen.getByRole('button', { name: 'Builder' }))

    expect(screen.getByText("The builder can't show this schema")).toBeInTheDocument()
    expect(screen.getByText(/Uses \$defs\./)).toHaveTextContent('top level: Uses $defs.')
    await user.click(screen.getByRole('button', { name: 'Edit as JSON' }))
    expect(screen.getByLabelText('JSON Schema')).toBeInTheDocument()
  })

  test('JSON edits show up in the builder when switching back', async () => {
    const { user } = openAs(lead, `${LIST}/new`)
    await editAsJson(user)
    setText(screen.getByLabelText('JSON Schema'), '{"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "integer"}}}}')
    await user.click(screen.getByRole('button', { name: 'Builder' }))

    expect(screen.getByLabelText('Name of lines')).toHaveValue('lines')
    expect(screen.getByRole('combobox', { name: 'Type of items of lines' })).toHaveTextContent('Whole number')
  })
})
