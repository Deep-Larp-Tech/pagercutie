import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import type { HTTPValidationError } from '@/api/generated/model'

/** Shown when a `422` names no field the form has. */
const INVALID_INPUT = 'Some values are not valid. Check the form and try again.'

/**
 * Puts each error of a FastAPI `422` under the form field its `loc` names (`['body', 'email']`), for the fields in
 * `fields`. Errors for any other location go to the form's root error, so none is lost.
 */
export function applyValidationErrors<T extends FieldValues>(
  setError: UseFormSetError<T>,
  error: HTTPValidationError,
  fields: readonly Path<T>[],
): void {
  const unplaced: string[] = []
  for (const { loc, msg } of error.detail ?? []) {
    const field = loc[0] === 'body' ? fields.find((name) => name === loc.at(-1)) : undefined
    if (field === undefined) unplaced.push(msg)
    else setError(field, { message: msg })
  }
  if (unplaced.length > 0 || error.detail === undefined || error.detail.length === 0) {
    setError('root', { message: unplaced[0] ?? INVALID_INPUT })
  }
}
