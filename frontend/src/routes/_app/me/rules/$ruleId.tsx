import { createFileRoute } from '@tanstack/react-router'
import { EditRulePage } from '@/components/rules/rule-builder-page'
import { usePersonalRuleScope } from '@/components/rules/rule-scope'

export const Route = createFileRoute('/_app/me/rules/$ruleId')({
  staticData: { title: 'Personal rule' },
  component: function PersonalRule() {
    const { ruleId } = Route.useParams()
    return <EditRulePage scope={usePersonalRuleScope()} ruleId={ruleId} />
  },
})
