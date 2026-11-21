import { describe, expect, test } from 'vitest'
import { insertPlaceholder, lookupPath, renderTemplate } from './templates'

const event = {
  source: 'trades',
  severity: 'error',
  payload: { currency: 'USD', notional: 12400000, reason: 'Limit breached', error: { code: 'TIMEOUT' } },
}

describe('renderTemplate', () => {
  test("Team Rates' title", () => {
    expect(renderTemplate('Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}', event)).toBe(
      'Rejected USD 12400000 — Limit breached',
    )
  })

  test('nested paths, spaces inside braces, unresolved placeholders stay', () => {
    expect(renderTemplate('{{ payload.error.code }} from {{source}}: {{payload.missing}}', event)).toBe(
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
