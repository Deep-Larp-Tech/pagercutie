import { useRouter, type ErrorComponentProps } from '@tanstack/react-router'
import { TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { UnexpectedStatusError } from '@/lib/api'
import { EmptyState } from './empty-state'

/** Shown in the shell's content area when one screen fails to load or render; the sidebar and header stay usable. */
export function ScreenError({ error, reset }: ErrorComponentProps) {
  const router = useRouter()
  const description =
    error instanceof UnexpectedStatusError
      ? error.message
      : 'Try again. If it keeps happening, reload the page or tell your admin.'
  return (
    <EmptyState
      icon={TriangleAlert}
      role="alert"
      title="Couldn't show this page"
      description={description}
      action={
        <Button
          variant="secondary"
          onClick={() => {
            reset()
            void router.invalidate()
          }}
        >
          Try again
        </Button>
      }
    />
  )
}
