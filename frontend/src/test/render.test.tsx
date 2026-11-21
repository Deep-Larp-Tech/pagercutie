import { useLocation } from '@tanstack/react-router'
import { expect, test } from 'vitest'
import { renderWithProviders } from './render'

function CurrentPath() {
  return <p>Path {useLocation({ select: (location) => location.pathname })}</p>
}

test('renders the element at the given route', async () => {
  const { findByText } = renderWithProviders(<CurrentPath />, { route: '/teams/payments/alerts' })

  expect(await findByText('Path /teams/payments/alerts')).toBeInTheDocument()
})
