import { createFileRoute } from '@tanstack/react-router'
import { EditRulePage } from '@/components/rules/rule-builder-page'
import { useTeamRuleScope } from '@/components/rules/rule-scope'

export const Route = createFileRoute('/_app/teams/$team/rules/$ruleId')({
  staticData: { title: 'Rule' },
  component: function TeamRule() {
    const { ruleId } = Route.useParams()
    return <EditRulePage scope={useTeamRuleScope()} ruleId={ruleId} />
  },
})
