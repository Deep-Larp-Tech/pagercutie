import { createFileRoute, redirect } from '@tanstack/react-router'

/** `/admin` opens the user list. */
export const Route = createFileRoute('/_app/admin/')({
  beforeLoad: () => {
    throw redirect({ to: '/admin/users', replace: true })
  },
})
