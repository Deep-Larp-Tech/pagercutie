import { describe, expect, test } from 'vitest'
import { renderTemplate } from './templates'

const payload = { workflowId: 'wf-8f21', amount: 12400000, error: { code: 'TIMEOUT' }, flag: null }

describe('renderTemplate', () => {
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
