import { describe, expect, test } from 'vitest'
import { RunbookFormat, type Condition } from '@/api/generated/model'
import { describeCondition, runbookFormatInfo, templateParts } from './runbooks'

describe('runbook formats', () => {
  test('every format has a label and a hint', () => {
    expect(Object.values(RunbookFormat).map((format) => runbookFormatInfo[format].label)).toEqual([
      'YAML',
      'Markdown',
      'Free text',
      'Link',
    ])
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
