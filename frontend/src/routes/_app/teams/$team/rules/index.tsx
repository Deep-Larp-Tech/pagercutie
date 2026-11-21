import { createFileRoute } from '@tanstack/react-router'
import { RulesPage } from '@/components/rules/rules-page'
import { useTeamRuleScope } from '@/components/rules/rule-scope'

export const Route = createFileRoute('/_app/teams/$team/rules/')({
  staticData: { title: 'Rules' },
  component: function TeamRules() {
    return <RulesPage scope={useTeamRuleScope()} />
  },
})
