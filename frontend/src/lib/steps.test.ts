import { describe, expect, test } from 'vitest'
import { StepDecisionKind, StepStatus, type Step } from '@/api/generated/model'
import {
  formatDuration,
  guardSentence,
  statusAfterDecision,
  stepDecisions,
  stepParameters,
  stepStatusLabel,
  stepSummary,
} from './steps'

const payload = { workflowId: 'wf-8f21' }

describe('step maps', () => {
  test('every status has words, and every decision a status after it', () => {
    for (const status of Object.values(StepStatus)) expect(stepStatusLabel[status]).not.toBe('')
    for (const kind of Object.values(StepDecisionKind)) {
      expect(Object.values(StepStatus)).toContain(statusAfterDecision[kind])
    }
  })

  test('only the three waiting statuses take decisions (DOMAIN.md §6)', () => {
    const deciding = Object.values(StepStatus).filter((status) => stepDecisions[status] !== null)
    expect(deciding).toEqual(['awaiting_approval', 'awaiting_answer', 'awaiting_manual'])
    expect(stepDecisions.awaiting_approval?.role).toBe('approver')
    expect(stepDecisions.awaiting_answer?.kinds).toEqual(['yes', 'no'])
  })
})

describe('stepParameters and stepSummary', () => {
  const cases: [Step, { label: string; value: string }[], string][] = [
    [
      { action: 'http_get', url: 'http://svc/{{workflowId}}' },
      [{ label: 'URL', value: 'http://svc/wf-8f21' }],
      'Sends a GET request to http://svc/wf-8f21.',
    ],
    [
      { action: 'call_webhook', url: 'http://hook', method: 'PUT' },
      [
        { label: 'Method', value: 'PUT' },
        { label: 'URL', value: 'http://hook' },
      ],
      'Sends a PUT request to http://hook.',
    ],
    [
      { action: 'retry_workflow', workflowId: '{{payload.workflowId}}' },
      [{ label: 'Workflow', value: 'wf-8f21' }],
      'Retries workflow wf-8f21.',
    ],
    [
      { action: 'restart_service', service: 'api' },
      [{ label: 'Service', value: 'api' }],
      'Restarts api.',
    ],
    [
      { action: 'open_ticket', title: 'Stuck {{workflowId}}' },
      [{ label: 'Title', value: 'Stuck wf-8f21' }],
      'Opens a ticket titled "Stuck wf-8f21".',
    ],
    [
      { action: 'escalate', team: 'support' },
      [{ label: 'Team', value: 'support' }],
      'Escalates the alert to team support, whose people get notified.',
    ],
    [
      { action: 'wait', seconds: 3661 },
      [{ label: 'Duration', value: '1 hour 1 minute 1 second' }],
      'Waits 1 hour 1 minute 1 second.',
    ],
    [
      { action: 'manual', text: 'Call {{workflowId}} owner' },
      [],
      'Call wf-8f21 owner',
    ],
  ]

  test.each(cases)('%o', (step, parameters, summary) => {
    expect(stepParameters(step, payload)).toEqual(parameters)
    expect(stepSummary(step, payload)).toBe(summary)
  })

  test('a webhook without a method uses the API default, POST', () => {
    const step: Step = { action: 'call_webhook', url: 'http://hook' }
    expect(stepSummary(step, payload)).toBe('Sends a POST request to http://hook.')
  })
})

describe('formatDuration and guardSentence', () => {
  test('durations in words', () => {
    expect(formatDuration(1)).toBe('1 second')
    expect(formatDuration(120)).toBe('2 minutes')
  })

  test('a structured guard numbers steps from 1', () => {
    expect(guardSentence({ step: 0, failures_gte: 1 })).toBe('Runs when step 1 has failed once or more.')
    expect(guardSentence({ step: 1, failures_gte: 2 })).toBe('Runs when step 2 has failed 2 times or more.')
  })
})
