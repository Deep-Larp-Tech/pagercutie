import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'

/** Router and query devtools; loaded only in development (see `routes/__root.tsx`). */
export default function Devtools() {
  return (
    <>
      <TanStackRouterDevtools position="bottom-left" />
      <ReactQueryDevtools buttonPosition="bottom-left" />
    </>
  )
}
