import { createFileRoute, redirect } from '@tanstack/react-router'

/** `/teams/$team/settings` opens General. */
export const Route = createFileRoute('/_app/teams/$team/settings/')({
  beforeLoad: ({ params }) => {
    throw redirect({ to: '/teams/$team/settings/general', params, replace: true })
  },
})
