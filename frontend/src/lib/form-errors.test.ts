import { describe, expect, test, vi } from 'vitest'
import { applyValidationErrors } from './form-errors'

interface Values {
  email: string
  name: string
}

describe('applyValidationErrors', () => {
  test('puts body errors under their field and anything else on the root', () => {
    const setError = vi.fn()
    applyValidationErrors<Values>(
      setError,
      {
        detail: [
          { loc: ['body', 'email'], msg: 'Bad email', type: 'value_error' },
          { loc: ['query', 'limit'], msg: 'Too big', type: 'value_error' },
        ],
      },
      ['email', 'name'],
    )
    expect(setError.mock.calls).toEqual([
      ['email', { message: 'Bad email' }],
      ['root', { message: 'Too big' }],
    ])
  })

  test('an empty list still tells the user something', () => {
    const setError = vi.fn()
    applyValidationErrors<Values>(setError, { detail: [] }, ['email'])
    expect(setError).toHaveBeenCalledWith('root', {
      message: 'Some values are not valid. Check the form and try again.',
    })
  })
})
