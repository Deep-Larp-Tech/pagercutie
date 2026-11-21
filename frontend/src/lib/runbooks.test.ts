import { describe, expect, test } from 'vitest'
import { RunbookFormat, type Condition, type Step } from '@/api/generated/model'
import {
  approvalCount,
  defaultApproval,
  describeCondition,
  duration,
  effectiveApproval,
  guardText,
  runbookFormatInfo,
  stepActionInfo,
  stepParameters,
  templateParts,
  type StepAction,
} from './runbooks'

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

describe('step action maps', () => {
  test('every action has an icon, a label, a summary and a default approval', () => {
    const actions: StepAction[] = everyStep.map((step) => step.action)
    for (const action of actions) {
      expect(stepActionInfo[action].label).not.toBe('')
      expect(stepActionInfo[action].summary).toMatch(/\.$/)
      expect(['none', 'required']).toContain(defaultApproval[action])
    }
    expect(Object.keys(stepActionInfo).sort()).toEqual([...actions].sort())
  })

  test('every format has a label and a hint', () => {
    expect(Object.values(RunbookFormat).map((format) => runbookFormatInfo[format].label)).toEqual([
      'YAML',
      'Markdown',
      'Free text',
      'Link',
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

describe('stepParameters', () => {
  test('lists what each action runs with', () => {
    expect(everyStep.map(stepParameters)).toEqual([
      [{ label: 'URL', value: 'http://counterparty-service/health', templated: true }],
      [{ label: 'Workflow', value: '{{workflowId}}', templated: true }],
      [{ label: 'Service', value: '{{payload.instance}}', templated: true }],
      [
        { label: 'Method', value: 'PUT', templated: false },
        { label: 'URL', value: 'https://hooks.example.com/{{payload.id}}', templated: true },
      ],
      [{ label: 'Title', value: 'Settlement {{workflowId}} stuck', templated: true }],
      [{ label: 'Team', value: 'counterparty-support', templated: false }],
      [{ label: 'For', value: '2 minutes', templated: false }],
      [],
    ])
  })

  test('a webhook without a method shows the default POST', () => {
    expect(stepParameters({ action: 'call_webhook', url: 'x' })[0]?.value).toBe('POST')
  })
})

test.each([
  [1, '1 second'],
  [90, '90 seconds'],
  [60, '1 minute'],
  [120, '2 minutes'],
  [3600, '1 hour'],
  [5400, '1 hour 30 minutes'],
])('duration(%i) is %s', (seconds, text) => {
  expect(duration(seconds)).toBe(text)
})

describe('guardText', () => {
  test('a parsed guard names the step and how often it failed', () => {
    expect(guardText({ step: 1, failures_gte: 2 }, everyStep)).toBe(
      'Only after step 2 (Retry workflow) has failed twice.',
    )
    expect(guardText({ step: 0, failures_gte: 1 }, everyStep)).toBe(
      'Only after step 1 (Check a URL) has failed once.',
    )
    expect(guardText({ step: 9, failures_gte: 3 }, everyStep)).toBe('Only after step 10 has failed 3 times.')
  })

  test('free text becomes a question a person answers', () => {
    expect(guardText('retry fails twice', everyStep)).toBe('A person answers first: "retry fails twice?"')
  })
})

describe('describeCondition', () => {
  test('the matches: block of the settlement runbook', () => {
    const matches: Condition = {
      op: 'and',
      args: [
        { op: 'eq', field: 'type', value: 'WORKFLOW_FAILED' },
        { op: 'eq', field: 'error.code', value: 'TIMEOUT' },
      ],
    }
    expect(describeCondition(matches)).toBe('type = WORKFLOW_FAILED and error.code = TIMEOUT')
  })

  test.each<[Condition, string]>([
    [{ op: 'ne', field: 'env', value: 'dev' }, 'env ≠ dev'],
    [{ op: 'gt', field: 'notional', value: 10_000_000 }, 'notional > 10000000'],
    [{ op: 'gte', field: 'n', value: 1 }, 'n ≥ 1'],
    [{ op: 'lt', field: 'n', value: 1 }, 'n < 1'],
    [{ op: 'lte', field: 'n', value: null }, 'n ≤ null'],
    [{ op: 'in', field: 'desk', value: ['rates', 'fx'] }, 'desk is one of rates, fx'],
    [{ op: 'not_in', field: 'desk', value: ['rates'] }, 'desk is none of rates'],
    [{ op: 'contains', field: 'tags', value: 'prod' }, 'tags contains prod'],
    [{ op: 'glob', field: 'source', value: 'pricing-engine-*' }, 'source matches pricing-engine-*'],
    [{ op: 'exists', field: 'workflowId' }, 'workflowId is set'],
    [{ op: 'not', arg: { op: 'exists', field: 'x' } }, 'not x is set'],
    [
      {
        op: 'or',
        args: [
          { op: 'eq', field: 'a', value: true },
          { op: 'and', args: [{ op: 'eq', field: 'b', value: 1 }, { op: 'eq', field: 'c', value: 2 }] },
        ],
      },
      'a = true or (b = 1 and c = 2)',
    ],
  ])('%j reads %s', (condition, text) => {
    expect(describeCondition(condition)).toBe(text)
  })
})

describe('templateParts', () => {
  test('splits placeholders from plain text', () => {
    expect(templateParts('Retry {{payload.workflowId}} now')).toEqual([
      { text: 'Retry ', placeholder: false },
      { text: '{{payload.workflowId}}', placeholder: true },
      { text: ' now', placeholder: false },
    ])
  })

  test('text without placeholders is one plain part', () => {
    expect(templateParts('http://x/health')).toEqual([{ text: 'http://x/health', placeholder: false }])
  })
})
