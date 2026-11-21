import { createFileRoute } from '@tanstack/react-router'
import { NewRulePage } from '@/components/rules/rule-builder-page'
import { usePersonalRuleScope } from '@/components/rules/rule-scope'

export const Route = createFileRoute('/_app/me/rules/new')({
  staticData: { title: 'New personal rule' },
  component: function NewPersonalRule() {
    return <NewRulePage scope={usePersonalRuleScope()} />
  },
})
