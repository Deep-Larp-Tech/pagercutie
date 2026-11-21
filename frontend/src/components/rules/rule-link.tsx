import type { ReactNode } from 'react'
import { Link } from '@tanstack/react-router'
import type { RuleScope } from './rule-scope'

/** Props for `RuleLink`. */
export interface RuleLinkProps {
  scope: RuleScope
  /** The rule to open; `'new'` opens an empty builder, `null` the list. */
  to: string | null
  className?: string
  children: ReactNode
}

/** Link to the scope's rule list, builder or one rule. */
export function RuleLink({ scope, to, className, children }: RuleLinkProps) {
  if (scope.kind === 'team') {
    const team = scope.team.slug
    if (to === null) return <Link to="/teams/$team/rules" params={{ team }} className={className}>{children}</Link>
    if (to === 'new') return <Link to="/teams/$team/rules/new" params={{ team }} className={className}>{children}</Link>
    return (
      <Link to="/teams/$team/rules/$ruleId" params={{ team, ruleId: to }} className={className}>
        {children}
      </Link>
    )
  }
  if (to === null) return <Link to="/me/rules" className={className}>{children}</Link>
  if (to === 'new') return <Link to="/me/rules/new" className={className}>{children}</Link>
  return (
    <Link to="/me/rules/$ruleId" params={{ ruleId: to }} className={className}>
      {children}
    </Link>
  )
}
