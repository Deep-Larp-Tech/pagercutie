import { describe, expect, test } from 'vitest'
import { describeParseError, findSyntaxProblem, isJsonObject, lineAndColumn, parseJson } from './json-text'

describe('parseJson', () => {
  test('returns the value of valid JSON', () => {
    expect(parseJson('{"a": [1, true, null]}')).toEqual({ ok: true, value: { a: [1, true, null] } })
  })

  test('points at the line and column of a syntax error, in plain words', () => {
    const result = parseJson('{\n  "a": 1,\n  }')

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(describeParseError(result)).toBe('Line 3, column 3: Remove the comma before the closing }.')
  })

  test('locates errors V8 reports without a position', () => {
    const result = parseJson('{\n  "properties": }')

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(describeParseError(result)).toMatch(/^Line 2, column 17: Expected a value/)
  })

  test('asks for JSON when the text is empty', () => {
    const result = parseJson('   ')

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(describeParseError(result)).toMatch(/JSON/)
  })
})

describe('lineAndColumn', () => {
  test('counts from 1', () => {
    expect(lineAndColumn('ab\ncd', 0)).toEqual({ line: 1, column: 1 })
    expect(lineAndColumn('ab\ncd', 4)).toEqual({ line: 2, column: 2 })
  })
})

describe('isJsonObject', () => {
  test('accepts objects only', () => {
    expect(isJsonObject({})).toBe(true)
    expect(isJsonObject([])).toBe(false)
    expect(isJsonObject(null)).toBe(false)
    expect(isJsonObject('x')).toBe(false)
  })
})

describe('findSyntaxProblem', () => {
  test.each([
    '{}',
    '[]',
    '{"a": [1, -2.5e3, true, false, null, "x\\n\\u00e9"], "b": {"c": {}}}',
    '  "text"  ',
    '0',
  ])('accepts valid JSON %s', (text) => {
    expect(findSyntaxProblem(text)).toBeNull()
  })

  test.each([
    ['{"a" 1}', 5, 'Expected a colon after the field name.'],
    ["{'a': 1}", 1, 'Expected a field name in double quotes.'],
    ['{"a": 1 "b": 2}', 8, 'Expected a comma or a closing }.'],
    ['[1 2]', 3, 'Expected a comma or a closing ].'],
    ['[1,]', 3, 'Remove the comma before the closing ].'],
    ['{"a": tru}', 6, 'Expected a value: an object, array, string, number, true, false or null.'],
    ['{"a": "x', 8, 'The JSON ends too early.'],
    ['{"a": "\\q"}', 8, 'Unknown escape in a string. Write a backslash as \\\\.'],
    ['{} x', 3, 'Unexpected text after the end of the JSON.'],
    ['{"a": 01}', 7, 'Expected a comma or a closing }.'],
  ])('%s fails at %i: %s', (text, offset, message) => {
    expect(findSyntaxProblem(text)).toEqual({ offset, message })
  })
})
