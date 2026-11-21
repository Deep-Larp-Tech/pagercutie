import type { RunbookParseResult, RunbookRead } from '@/api/generated/model'
import { runbookExamples, type RunbookExample } from '@/lib/runbook-examples'
import { settlements } from './teams'

/** A runbook of Team Settlements with a fixed id derived from its slug. */
export function runbook(slug: string, overrides: Partial<RunbookRead> = {}): RunbookRead {
  return {
    id: `runbook-${slug}`,
    slug,
    title: slug,
    team_id: settlements.id,
    format: 'markdown',
    original: '1. Check the dashboard.',
    attach: null,
    steps: [{ action: 'manual', text: 'Check the dashboard.' }],
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    ...overrides,
  }
}

/** The example from REQUIREMENTS.md §6.2 with `id`. */
export function example(id: RunbookExample['id']): RunbookExample {
  const found = runbookExamples.find((candidate) => candidate.id === id)
  if (found === undefined) throw new Error(`no example ${id}`)
  return found
}

/** What the server returns for each §6.2 sample, per SPEC §11.1. */
export const parsedExamples = {
  'settlement-timeout': {
    attach: {
      op: 'and',
      args: [
        { op: 'eq', field: 'type', value: 'WORKFLOW_FAILED' },
        { op: 'eq', field: 'error.code', value: 'TIMEOUT' },
      ],
    },
    steps: [
      { check: 'Is counterparty-service healthy?', action: 'http_get', url: 'http://counterparty-service/health' },
      { action: 'retry_workflow', workflowId: '{{workflowId}}', approval: 'none' },
      { if: { step: 1, failures_gte: 2 }, action: 'escalate', team: 'counterparty-support', approval: 'required' },
    ],
    warnings: [],
  },
  'payments-error-rate': {
    attach: null,
    steps: [
      { action: 'manual', text: 'Open the payments dashboard and check if errors are in one region only.' },
      {
        action: 'manual',
        text: 'If one region: fail traffic over to the other region (needs approval from the team lead).',
      },
      { action: 'manual', text: 'If all regions: check the last deployment and roll it back.' },
      { action: 'manual', text: 'Post an update in the #payments-incidents channel every 15 minutes.' },
    ],
    warnings: ['Markdown list items became manual steps.'],
  },
  'pricing-latency': {
    attach: null,
    steps: [{ action: 'manual', text: example('pricing-latency').original.trim() }],
    warnings: ['Free text is kept as one manual step.'],
  },
} satisfies Record<RunbookExample['id'], RunbookParseResult>
