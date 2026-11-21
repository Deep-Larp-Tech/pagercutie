import { Link } from '@tanstack/react-router'
import { Lock } from 'lucide-react'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { buttonVariants } from '@/components/ui/styles'
import { READ_ONLY } from './messages'
import { RunbookEditor } from './runbook-editor'
import { useRunbookScope } from './use-runbook-scope'

/** `/teams/$team/runbooks/new`: the editor for members and leads; viewers get a line saying who can add runbooks. */
export function NewRunbookPage() {
  const { team, canEdit } = useRunbookScope()
  if (canEdit) return <RunbookEditor />
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="New runbook" />
      <EmptyState
        icon={Lock}
        title={READ_ONLY}
        description="Ask a team lead to make you a member if you need to add one."
        action={
          <Link to="/teams/$team/runbooks" params={{ team: team.slug }} className={buttonVariants({ variant: 'secondary' })}>
            Back to runbooks
          </Link>
        }
      />
    </div>
  )
}
