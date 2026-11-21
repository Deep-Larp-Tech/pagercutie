import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { createQueryClient } from './lib/query'
import { createAppRouter } from './router'
import './index.css'

async function enableMocks() {
  if (import.meta.env.VITE_MOCK !== '1') return
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledFrame: 'bypass' })
}

const queryClient = createQueryClient()
const router = createAppRouter(queryClient)

function render() {
  const root = document.getElementById('root')
  if (!root) throw new Error('index.html has no #root element')
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  )
}

// The worker must be running before the first query fires, or that request reaches the real backend.
void enableMocks().then(render)
