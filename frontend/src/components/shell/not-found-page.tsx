import { Link } from '@tanstack/react-router'
import { MapPinOff } from 'lucide-react'
import { buttonVariants } from '@/components/ui/styles'
import { EmptyState } from './empty-state'

/** 404 content: the page does not exist or the user may not see it; the two are not told apart. */
export function NotFoundPage() {
  return (
    <EmptyState
      icon={MapPinOff}
      role="alert"
      title="Page not found"
      description="This page doesn't exist, or you don't have access to it. Check the link or ask whoever sent it."
      action={
        <Link to="/" className={buttonVariants({ variant: 'secondary' })}>
          Go to overview
        </Link>
      }
    />
  )
}
