import { describe, expect, test } from 'vitest'
import { StepDecisionKind, StepStatus, type Step } from '@/api/generated/model'
import {
  approvalCount,
  defaultApproval,
  effectiveApproval,
  formatDuration,
  guardText,
  statusAfterDecision,
  stepActionInfo,
  stepDecisions,
  stepParameters,
  stepStatusLabel,
  stepSummary,
  type StepAction,
} from './steps'

const payload = { workflowId: 'wf-8f21' }

const everyStep = [
  { action: 'http_get', url: 'http://counterparty-service/health' },
  { action: 'retry_workflow', workflowId: '{{workflowId}}' },
  { action: 'restart_service', service: '{{payload.instance}}' },
  { action: 'call_webhook', url: 'https://hooks.example.com/{{payload.id}}', method: 'PUT' },
  { action: 'open_ticket', title: 'Settlement {{workflowId}} stuck' },
  { action: 'escalate', team: 'counterparty-support' },
  { action: 'wait', seconds: 120 },
  { action: 'manual', text: 'Check the dashboard.' },
] as const satisfies readonly Step[]

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
  const cases: [Step, { label: string; value: string; templated: boolean }[], string][] = [
    [
      { action: 'http_get', url: 'http://svc/{{workflowId}}' },
      [{ label: 'URL', value: 'http://svc/wf-8f21', templated: true }],
      'Sends a GET request to http://svc/wf-8f21.',
    ],
    [
      { action: 'call_webhook', url: 'http://hook', method: 'PUT' },
      [
        { label: 'Method', value: 'PUT', templated: false },
        { label: 'URL', value: 'http://hook', templated: true },
      ],
      'Sends a PUT request to http://hook.',
    ],
    [
      { action: 'retry_workflow', workflowId: '{{payload.workflowId}}' },
      [{ label: 'Workflow', value: 'wf-8f21', templated: true }],
      'Retries workflow wf-8f21.',
    ],
    [
      { action: 'restart_service', service: 'api' },
      [{ label: 'Service', value: 'api', templated: true }],
      'Restarts api.',
    ],
    [
      { action: 'open_ticket', title: 'Stuck {{workflowId}}' },
      [{ label: 'Title', value: 'Stuck wf-8f21', templated: true }],
      'Opens a ticket titled "Stuck wf-8f21".',
    ],
    [
      { action: 'escalate', team: 'support' },
      [{ label: 'Team', value: 'support', templated: false }],
      'Escalates the alert to team support, whose people get notified.',
    ],
    [
      { action: 'wait', seconds: 3661 },
      [{ label: 'Duration', value: '1 hour 1 minute 1 second', templated: false }],
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

describe('step action maps', () => {
  test('every action has an icon, a label, a description and a default approval', () => {
    const actions: StepAction[] = everyStep.map((step) => step.action)
    for (const action of actions) {
      expect(stepActionInfo[action].label).not.toBe('')
      expect(stepActionInfo[action].description).toMatch(/\.$/)
      expect(['none', 'required']).toContain(defaultApproval[action])
    }
    expect(Object.keys(stepActionInfo).sort()).toEqual([...actions].sort())
  })
})

describe('stepParameters without a payload', () => {
  test('keeps placeholders as written and marks the values that may hold them', () => {
    expect(everyStep.map((step) => stepParameters(step))).toEqual([
      [{ label: 'URL', value: 'http://counterparty-service/health', templated: true }],
      [{ label: 'Workflow', value: '{{workflowId}}', templated: true }],
      [{ label: 'Service', value: '{{payload.instance}}', templated: true }],
      [
        { label: 'Method', value: 'PUT', templated: false },
        { label: 'URL', value: 'https://hooks.example.com/{{payload.id}}', templated: true },
      ],
      [{ label: 'Title', value: 'Settlement {{workflowId}} stuck', templated: true }],
      [{ label: 'Team', value: 'counterparty-support', templated: false }],
      [{ label: 'Duration', value: '2 minutes', templated: false }],
      [],
    ])
  })
})

describe('effectiveApproval', () => {
  test('uses the default when the step sets none', () => {
    expect(effectiveApproval({ action: 'http_get', url: 'x' })).toBe('none')
    expect(effectiveApproval({ action: 'escalate', team: 'ops' })).toBe('required')
  })

  test('a step may make an action stricter', () => {
    expect(effectiveApproval({ action: 'http_get', url: 'x', approval: 'required' })).toBe('required')
  })

  test('a step cannot make an action looser (ADR-0019)', () => {
    expect(effectiveApproval({ action: 'restart_service', service: 'x', approval: 'none' })).toBe('required')
  })

  test('approvalCount counts the steps that wait for a lead', () => {
    expect(approvalCount(everyStep)).toBe(3)
  })
})

test.each([
  [1, '1 second'],
  [90, '1 minute 30 seconds'],
  [120, '2 minutes'],
  [3600, '1 hour'],
  [5400, '1 hour 30 minutes'],
])('formatDuration(%i) is %s', (seconds, text) => {
  expect(formatDuration(seconds)).toBe(text)
})

describe('guardText', () => {
  test('a structured guard numbers steps from 1 and names the step when it is known', () => {
    expect(guardText({ step: 1, failures_gte: 2 }, everyStep)).toBe(
      'Runs when step 2 (Retry the workflow) has failed twice or more.',
    )
    expect(guardText({ step: 0, failures_gte: 1 })).toBe('Runs when step 1 has failed once or more.')
    expect(guardText({ step: 9, failures_gte: 3 }, everyStep)).toBe('Runs when step 10 has failed 3 times or more.')
  })

  test('free text becomes a question a person answers', () => {
    expect(guardText('retry fails twice')).toBe('A person answers first: "retry fails twice?"')
  })
})
