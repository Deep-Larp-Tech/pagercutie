import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { waitFor } from '@testing-library/react'
import { getListRunbooksUrl, listRunbooks } from '@/api/generated/runbooks/runbooks'
import { respond } from '@/test/http'
import { parsedExamples, runbook } from '@/test/runbooks'
import { server } from '@/test/server'
import { openAs, petraIn, recordRequests, settlements } from '@/test/teams'

const PATH = '/teams/settlements/runbooks'

const settlementTimeout = runbook('settlement-timeout', {
  title: 'Settlement timeout',
  format: 'structured',
  attach: parsedExamples['settlement-timeout'].attach,
  steps: parsedExamples['settlement-timeout'].steps,
})

function listing(runbooks = [settlementTimeout]) {
  return respond(listRunbooks, 'get', getListRunbooksUrl(), 200, runbooks)
}

describe('GET /runbooks', () => {
  test("lists the team's runbooks with format, step counts and condition", async () => {
    server.use(listing())
    const sent = recordRequests('get', '/api/runbooks')

    const { findByRole } = openAs(petraIn('member'), PATH)

    const link = await findByRole('link', { name: 'Settlement timeout' })
    expect(link).toHaveAttribute('href', '/teams/settlements/runbooks/runbook-settlement-timeout')
    const row = link.closest('tr')
    if (row === null) throw new Error('no row')
    const cells = [...row.querySelectorAll('td')].map((cell) => cell.textContent)
    expect(cells.slice(0, 6)).toEqual([
      'Settlement timeout',
      'settlement-timeout',
      'YAML',
      '3',
      '1',
      'type = WORKFLOW_FAILED and error.code = TIMEOUT',
    ])
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0]?.path).toBe('/api/runbooks')
  })

  test('asks for the team in the URL only', async () => {
    let query: URLSearchParams | undefined
    server.use(
      http.get(getListRunbooksUrl(), ({ request }) => {
        query = new URL(request.url).searchParams
        return HttpResponse.json([])
      }),
    )

    const { findByText } = openAs(petraIn('member'), PATH)

    await findByText('No runbooks yet')
    expect(query?.get('team_id')).toBe(settlements.id)
    expect(query?.get('limit')).toBe('100')
  })

  test('a runbook without a condition says it applies through rules', async () => {
    server.use(listing([runbook('checklist')]))

    const { findByText } = openAs(petraIn('member'), PATH)

    expect(await findByText('Through rules')).toBeInTheDocument()
  })

  test('shows skeleton rows while loading', async () => {
    server.use(http.get(getListRunbooksUrl(), () => delay('infinite')))

    const { findAllByTestId } = openAs(petraIn('member'), PATH)

    expect(await findAllByTestId('skeleton-row')).toHaveLength(5)
  })

  test('a member gets New runbook and an empty state that points at it', async () => {
    server.use(listing([]))

    const { findByText, getByRole } = openAs(petraIn('member'), PATH)

    expect(await findByText('Add one with New runbook. Rules that name it show its steps on their alerts.')).toBeVisible()
    expect(getByRole('link', { name: 'New runbook' })).toHaveAttribute('href', '/teams/settlements/runbooks/new')
  })

  test('a viewer reads the list without New runbook and sees who can change it', async () => {
    server.use(listing())

    const { findByRole, queryByRole, getByText } = openAs(petraIn('viewer'), PATH)

    expect(await findByRole('link', { name: 'Settlement timeout' })).toBeVisible()
    expect(getByText('Only members and leads can change runbooks.')).toBeVisible()
    expect(queryByRole('link', { name: 'New runbook' })).not.toBeInTheDocument()
  })

  test('422 shows the error state with Try again', async () => {
    server.use(respond(listRunbooks, 'get', getListRunbooksUrl(), 422, { detail: [] }))

    const { findByRole, getByRole } = openAs(petraIn('member'), PATH)

    expect(await findByRole('alert')).toHaveTextContent("Couldn't load runbooks")
    expect(getByRole('button', { name: 'Try again' })).toBeVisible()
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(http.get(getListRunbooksUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole } = openAs(petraIn('member'), PATH)

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
