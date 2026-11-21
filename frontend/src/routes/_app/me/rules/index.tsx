import { createFileRoute } from '@tanstack/react-router'
import { RulesPage } from '@/components/rules/rules-page'
import { usePersonalRuleScope } from '@/components/rules/rule-scope'

export const Route = createFileRoute('/_app/me/rules/')({
  staticData: { title: 'My rules' },
  component: function MyRules() {
    return <RulesPage scope={usePersonalRuleScope()} />
  },
})
