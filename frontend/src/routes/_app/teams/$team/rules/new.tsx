import { createFileRoute } from '@tanstack/react-router'
import { NewRulePage } from '@/components/rules/rule-builder-page'
import { useTeamRuleScope } from '@/components/rules/rule-scope'

export const Route = createFileRoute('/_app/teams/$team/rules/new')({
  staticData: { title: 'New rule' },
  component: function NewTeamRule() {
    return <NewRulePage scope={useTeamRuleScope()} />
  },
})
