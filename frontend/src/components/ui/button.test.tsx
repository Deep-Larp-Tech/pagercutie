import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import { Button } from './button'

test('primary md is the default', () => {
  render(<Button>Acknowledge</Button>)

  const button = screen.getByRole('button', { name: 'Acknowledge' })
  expect(button).toHaveClass('bg-primary', 'h-8', 'rounded-md', 'active:scale-97')
})

test('variant and size change the classes', () => {
  render(
    <Button variant="destructive" size="sm">
      Delete rule
    </Button>,
  )

  const button = screen.getByRole('button', { name: 'Delete rule' })
  expect(button).toHaveClass('bg-destructive', 'h-7')
  expect(button).not.toHaveClass('bg-primary', 'h-8')
})

test('a disabled button ignores clicks', async () => {
  const onClick = vi.fn()
  render(
    <Button disabled onClick={onClick}>
      Resolve
    </Button>,
  )

  const button = screen.getByRole('button', { name: 'Resolve' })
  await userEvent.click(button)

  expect(button).toBeDisabled()
  expect(onClick).not.toHaveBeenCalled()
})
