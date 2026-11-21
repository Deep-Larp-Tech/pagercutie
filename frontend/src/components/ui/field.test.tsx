import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Field, FieldDescription, FieldError, FieldLabel } from './field'
import { Input } from './input'

test('links label, description and error to the input', () => {
  render(
    <Field invalid>
      <FieldLabel>Webhook URL</FieldLabel>
      <Input />
      <FieldDescription>Must start with https://.</FieldDescription>
      <FieldError>Couldn't save the step.</FieldError>
    </Field>,
  )

  const input = screen.getByLabelText('Webhook URL')
  const describedBy = input.getAttribute('aria-describedby') ?? ''
  const ids = describedBy.split(' ')
  expect(ids).toContain(screen.getByText('Must start with https://.').id)
  expect(ids).toContain(screen.getByText("Couldn't save the step.").id)
  expect(input).toHaveAttribute('aria-invalid', 'true')
  expect(input).toHaveAttribute('data-invalid')
})
