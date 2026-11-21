import type { CompareOp, Condition, RunbookFormat, Scalar } from '@/api/generated/model'

/** Label and helper text per input format (SPEC §11.1). */
export const runbookFormatInfo = {
  structured: { label: 'YAML', hint: 'Structured steps. Each step becomes an action; matches: sets when it applies.' },
  markdown: { label: 'Markdown', hint: 'Each numbered or bulleted item becomes a step a person ticks off.' },
  text: { label: 'Free text', hint: 'Kept as written and shown as one step a person follows.' },
  link: { label: 'Link', hint: 'A link to a wiki or Confluence page, shown as one step: open the runbook.' },
} as const satisfies Record<RunbookFormat, { label: string; hint: string }>

const compareSymbol = {
  eq: '=',
  ne: '≠',
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
} as const satisfies Record<CompareOp, string>

function scalar(value: Scalar): string {
  return value === null ? 'null' : String(value)
}

function nested(condition: Condition): string {
  const text = describeCondition(condition)
  return condition.op === 'and' || condition.op === 'or' ? `(${text})` : text
}

/** A condition as one line, e.g. `type = WORKFLOW_FAILED and error.code = TIMEOUT`. */
export function describeCondition(condition: Condition): string {
  switch (condition.op) {
    case 'and':
      return condition.args.map(nested).join(' and ')
    case 'or':
      return condition.args.map(nested).join(' or ')
    case 'not':
      return `not ${nested(condition.arg)}`
    case 'eq':
    case 'ne':
    case 'gt':
    case 'gte':
    case 'lt':
    case 'lte':
      return `${condition.field} ${compareSymbol[condition.op]} ${scalar(condition.value)}`
    case 'in':
      return `${condition.field} is one of ${condition.value.map(scalar).join(', ')}`
    case 'not_in':
      return `${condition.field} is none of ${condition.value.map(scalar).join(', ')}`
    case 'contains':
      return `${condition.field} contains ${scalar(condition.value)}`
    case 'glob':
      return `${condition.field} matches ${condition.value}`
    case 'exists':
      return `${condition.field} is set`
    default:
      return condition satisfies never
  }
}

/** Splits text into plain parts and `{{…}}` placeholders, in order, so placeholders can be highlighted. */
export function templateParts(text: string): { text: string; placeholder: boolean }[] {
  return text
    .split(/(\{\{[^{}]*\}\})/)
    .filter((part) => part !== '')
    .map((part) => ({ text: part, placeholder: /^\{\{[^{}]*\}\}$/.test(part) }))
}
