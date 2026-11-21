import { describe, expect, test } from 'vitest'
import { insertPlaceholder, lookupPath, renderEventTemplate, renderTemplate } from './templates'

const payload = { workflowId: 'wf-8f21', amount: 12400000, error: { code: 'TIMEOUT' }, flag: null }

describe('renderTemplate (runbook steps)', () => {
  test('fills both the short and the payload form (SPEC §11.2)', () => {
    expect(renderTemplate('retry {{workflowId}} / {{payload.workflowId}}', payload)).toBe('retry wf-8f21 / wf-8f21')
  })

  test('reads nested paths and allows spaces inside the braces', () => {
    expect(renderTemplate('{{ error.code }}', payload)).toBe('TIMEOUT')
  })

  test('groups numbers and writes other values as JSON', () => {
    expect(renderTemplate('{{amount}} {{error}} {{flag}}', payload)).toBe('12,400,000 {"code":"TIMEOUT"} null')
  })

  test('keeps a placeholder the payload has no value for', () => {
    expect(renderTemplate('http://x/{{missing.path}}', payload)).toBe('http://x/{{missing.path}}')
  })
})

const event = {
  source: 'trades',
  severity: 'error',
  payload: { currency: 'USD', notional: 12400000, reason: 'Limit breached', error: { code: 'TIMEOUT' } },
}

describe('renderEventTemplate (rule presentation)', () => {
  test("Team Rates' title", () => {
    expect(renderEventTemplate('Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}', event)).toBe(
      'Rejected USD 12400000 — Limit breached',
    )
  })

  test('nested paths, spaces inside braces, unresolved placeholders stay', () => {
    expect(renderEventTemplate('{{ payload.error.code }} from {{source}}: {{payload.missing}}', event)).toBe(
      'TIMEOUT from trades: {{payload.missing}}',
    )
  })

  test('lookupPath returns undefined past a scalar', () => {
    expect(lookupPath(event, 'payload.currency.code')).toBeUndefined()
  })
})

describe('insertPlaceholder', () => {
  test('inserts at the caret, or at the end without one', () => {
    expect(insertPlaceholder('Settlement  failed', 'payload.workflowId', 11)).toEqual({
      text: 'Settlement {{payload.workflowId}} failed',
      caret: 33,
    })
    expect(insertPlaceholder('Failed: ', 'payload.step', null)).toEqual({ text: 'Failed: {{payload.step}}', caret: 24 })
  })
})
