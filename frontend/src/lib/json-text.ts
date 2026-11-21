/** A JSON object: what an event payload and a JSON Schema document must be at the top level. */
export type JsonObject = { [key: string]: unknown }

/** Outcome of parsing JSON typed by a person. */
export type JsonParse =
  /** The text is valid JSON. */
  | { ok: true; value: unknown }
  /** The text is not valid JSON; `line` and `column` (1-based) point at the problem. */
  | { ok: false; message: string; line: number | null; column: number | null }

/** Whether `value` is a JSON object (not an array and not `null`). */
export function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 1-based line and column of character `offset` in `text`. */
export function lineAndColumn(text: string, offset: number): { line: number; column: number } {
  const before = text.slice(0, offset).split('\n')
  return { line: before.length, column: (before.at(-1)?.length ?? 0) + 1 }
}

/** Where a JSON text first breaks the grammar, and what was expected there. */
interface SyntaxProblem {
  offset: number
  message: string
}

class SyntaxStop extends Error {
  readonly problem: SyntaxProblem

  constructor(problem: SyntaxProblem) {
    super(problem.message)
    this.problem = problem
  }
}

const NUMBER = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y
const ESCAPES = '"\\/bfnrt'

/**
 * Finds the first syntax error in `text` by walking the JSON grammar (RFC 8259); `null` when the text is valid.
 * Engines word `JSON.parse` errors differently and V8 leaves the offset out of some, so the editor uses this instead.
 */
export function findSyntaxProblem(text: string): SyntaxProblem | null {
  let at = 0
  const stop = (message: string): never => {
    throw new SyntaxStop({ offset: at, message: at >= text.length ? 'The JSON ends too early.' : message })
  }
  const skipSpace = () => {
    while (at < text.length && ' \t\n\r'.includes(text.charAt(at))) at++
  }
  const literal = (word: string) => {
    if (!text.startsWith(word, at)) stop('Expected a value: an object, array, string, number, true, false or null.')
    at += word.length
  }
  const string = () => {
    at++
    while (at < text.length) {
      const char = text.charAt(at)
      if (char === '"') {
        at++
        return
      }
      if (char === '\\') {
        at++
        const escape = text.charAt(at)
        if (escape === 'u') {
          if (!/^[0-9a-fA-F]{4}$/.test(text.slice(at + 1, at + 5))) stop('Expected four hex digits after \\u.')
          at += 5
        } else if (ESCAPES.includes(escape) && escape !== '') {
          at++
        } else {
          stop('Unknown escape in a string. Write a backslash as \\\\.')
        }
      } else if (char < ' ') {
        stop('Line breaks and tabs inside a string must be written as \\n and \\t.')
      } else {
        at++
      }
    }
    stop('A string is missing its closing quote.')
  }
  const value = (): void => {
    skipSpace()
    const char = text.charAt(at)
    if (char === '{') return object()
    if (char === '[') return array()
    if (char === '"') return string()
    if (char === 't') return literal('true')
    if (char === 'f') return literal('false')
    if (char === 'n') return literal('null')
    NUMBER.lastIndex = at
    const number = NUMBER.exec(text)
    if (number === null) stop('Expected a value: an object, array, string, number, true, false or null.')
    else at += number[0].length
  }
  const object = () => {
    at++
    skipSpace()
    if (text.charAt(at) === '}') {
      at++
      return
    }
    for (;;) {
      skipSpace()
      if (text.charAt(at) !== '"') stop('Expected a field name in double quotes.')
      string()
      skipSpace()
      if (text.charAt(at) !== ':') stop('Expected a colon after the field name.')
      at++
      value()
      skipSpace()
      const next = text.charAt(at)
      at++
      if (next === '}') return
      if (next !== ',') {
        at--
        stop('Expected a comma or a closing }.')
      }
      skipSpace()
      if (text.charAt(at) === '}') stop('Remove the comma before the closing }.')
    }
  }
  const array = () => {
    at++
    skipSpace()
    if (text.charAt(at) === ']') {
      at++
      return
    }
    for (;;) {
      value()
      skipSpace()
      const next = text.charAt(at)
      at++
      if (next === ']') return
      if (next !== ',') {
        at--
        stop('Expected a comma or a closing ].')
      }
      skipSpace()
      if (text.charAt(at) === ']') stop('Remove the comma before the closing ].')
    }
  }

  try {
    if (text.trim() === '') return { offset: 0, message: 'Enter some JSON.' }
    value()
    skipSpace()
    if (at < text.length) stop('Unexpected text after the end of the JSON.')
    return null
  } catch (error) {
    if (error instanceof SyntaxStop) return error.problem
    throw error
  }
}

/** Parses `text` as JSON; a failure says where and what in plain words. */
export function parseJson(text: string): JsonParse {
  try {
    const value: unknown = JSON.parse(text)
    return { ok: true, value }
  } catch (error) {
    const problem = findSyntaxProblem(text)
    if (problem === null) {
      return { ok: false, message: error instanceof Error ? error.message : String(error), line: null, column: null }
    }
    if (text.trim() === '') return { ok: false, message: problem.message, line: null, column: null }
    return { ok: false, message: problem.message, ...lineAndColumn(text, problem.offset) }
  }
}

/** One-line description of a failed parse for the field under the editor, e.g. "Line 3, column 5: Expected …". */
export function describeParseError(result: Extract<JsonParse, { ok: false }>): string {
  return result.line === null ? result.message : `Line ${result.line}, column ${result.column}: ${result.message}`
}
