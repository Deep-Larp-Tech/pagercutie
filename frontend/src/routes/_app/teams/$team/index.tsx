import { createFileRoute, redirect } from '@tanstack/react-router'

/** `/teams/$team` opens the team's alerts. */
export const Route = createFileRoute('/_app/teams/$team/')({
  beforeLoad: ({ params }) => {
    throw redirect({ to: '/teams/$team/alerts', params, replace: true })
  },
})
