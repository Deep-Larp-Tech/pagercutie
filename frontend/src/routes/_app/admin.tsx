import { createFileRoute, notFound, Outlet } from '@tanstack/react-router'
import { NotFoundPage } from '@/components/shell/not-found-page'
import { can } from '@/lib/permissions'

/** Admin pages; anyone else gets the 404 page, as if the pages did not exist. */
export const Route = createFileRoute('/_app/admin')({
  beforeLoad: ({ context: { me } }) => {
    if (!can(me, 'users-and-teams.manage')) throw notFound()
  },
  component: Outlet,
  notFoundComponent: NotFoundPage,
})
