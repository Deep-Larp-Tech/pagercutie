import type { RunbookFormat } from '@/api/generated/model'

/** One of the sample runbooks from REQUIREMENTS.md §6.2, inserted with one click to show `RUN-8`. */
export interface RunbookExample {
  id: 'settlement-timeout' | 'payments-error-rate' | 'pricing-latency'
  /** Menu label: the format and what the runbook is for. */
  label: string
  format: RunbookFormat
  /** Title filled in when the title field is empty. */
  title: string
  original: string
}

export const runbookExamples: readonly RunbookExample[] = [
  {
    id: 'settlement-timeout',
    label: 'YAML: settlement timeout',
    format: 'structured',
    title: 'Settlement timeout',
    original: `runbook: settlement-timeout
matches:
  type: WORKFLOW_FAILED
  "error.code": TIMEOUT
steps:
  - check: "Is counterparty-service healthy?"
    action: http_get
    url: "http://counterparty-service/health"
  - action: retry_workflow
    workflowId: "{{workflowId}}"
    approval: none
  - if: "retry fails twice"
    action: escalate
    team: counterparty-support
    approval: required
`,
  },
  {
    id: 'payments-error-rate',
    label: 'Markdown: payments error rate',
    format: 'markdown',
    title: 'HighErrorRate on payments-api',
    original: `# HighErrorRate on payments-api
1. Open the payments dashboard and check if errors are in one region only.
2. If one region: fail traffic over to the other region (needs approval from the team lead).
3. If all regions: check the last deployment and roll it back.
4. Post an update in the #payments-incidents channel every 15 minutes.
`,
  },
  {
    id: 'pricing-latency',
    label: 'Free text: pricing latency',
    format: 'text',
    title: 'Pricing latency',
    original:
      "When pricing latency goes over a second, it's usually the cache. Restart the pricing-engine instance named in " +
      'the alert, wait 2 minutes, and if latency is still high, call the pricing on-call person.\n',
  },
]
