import { describe, expect, test } from 'vitest'
import { mergeFields, schemaFields } from './event-fields'

/** A workflow event like Team Settlements' (REQUIREMENTS.md §6.1). */
const workflowSchema = {
  type: 'object',
  properties: {
    type: { type: 'string', enum: ['WORKFLOW_FAILED', 'WORKFLOW_DONE'] },
    workflowId: { type: 'string', description: 'Workflow run id' },
    attempt: { type: 'integer' },
    error: { $ref: '#/$defs/Error' },
    tags: { type: 'array', items: { type: 'string' } },
  },
  $defs: {
    Error: {
      type: ['object', 'null'],
      properties: { code: { type: 'string' }, message: { type: 'string' }, cause: { $ref: '#/$defs/Error' } },
    },
  },
}

describe('schemaFields', () => {
  test('lists nested paths with their types, resolves $ref, stops on recursion', () => {
    const fields = schemaFields(workflowSchema)

    expect(fields.slice(0, 8).map(({ path, type }) => [path, type])).toEqual([
      ['payload.type', 'string'],
      ['payload.workflowId', 'string'],
      ['payload.attempt', 'number'],
      ['payload.error', 'object'],
      ['payload.error.code', 'string'],
      ['payload.error.message', 'string'],
      ['payload.error.cause', 'object'],
      ['payload.error.cause.code', 'string'],
    ])
    expect(fields.find(({ path }) => path === 'payload.tags')?.type).toBe('array')
    expect(fields.find(({ path }) => path === 'payload.type')?.values).toEqual(['WORKFLOW_FAILED', 'WORKFLOW_DONE'])
    expect(fields.find(({ path }) => path === 'payload.workflowId')?.description).toBe('Workflow run id')
    expect(fields.length).toBeLessThan(60)
  })

  test('a schema without properties gives no payload fields', () => {
    expect(schemaFields({ type: 'object' })).toEqual([])
    expect(schemaFields({})).toEqual([])
  })
})

describe('mergeFields', () => {
  test('metadata comes first; disagreeing types become unknown', () => {
    const fields = mergeFields([
      { properties: { amount: { type: 'number' }, desk: { type: 'string' } } },
      { properties: { amount: { type: 'string' } } },
    ])

    expect(fields.map(({ path, type }) => `${path}:${type}`)).toEqual([
      'source:string',
      'severity:severity',
      'schema:string',
      'schema_id:string',
      'payload.amount:unknown',
      'payload.desk:string',
    ])
  })
})
