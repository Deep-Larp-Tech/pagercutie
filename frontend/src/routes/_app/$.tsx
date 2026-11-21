import { createFileRoute } from '@tanstack/react-router'
import { NotFoundPage } from '@/components/shell/not-found-page'

/** Any path no other route matches, for a signed-in user: the 404 page inside the shell. */
export const Route = createFileRoute('/_app/$')({
  staticData: { title: 'Page not found' },
  component: NotFoundPage,
})
