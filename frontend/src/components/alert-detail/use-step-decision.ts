import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  getGetAlertQueryKey,
  getGetRunbookRunQueryKey,
  useDecideStep,
  type getRunbookRunResponse,
} from '@/api/generated/alerts/alerts'
import { getListAuditEntriesQueryKey } from '@/api/generated/audit/audit'
import type { StepDecisionKind, StepRunRead } from '@/api/generated/model'
import { unexpectedStatusMessage } from '@/lib/api'
import { statusAfterDecision } from '@/lib/steps'
import { useMe } from '@/lib/session'

/** Toast after each accepted decision. */
const decided = {
  approve: 'Step approved',
  reject: 'Step rejected',
  yes: 'Answered yes',
  no: 'Answered no',
  done: 'Step marked as done',
} as const satisfies Record<StepDecisionKind, string>

const offline = "Couldn't reach the server. Check your connection and try again."
const changed = 'Someone else decided this step first, or it moved on. The list now shows its current state.'
const forbidden = {
  approve: 'Only a team lead can approve this step.',
  reject: 'Only a team lead can reject this step.',
  yes: "You can't answer this question. Ask a team lead for the member role.",
  no: "You can't answer this question. Ask a team lead for the member role.",
  done: "You can't mark this step as done. Ask a team lead for the member role.",
} as const satisfies Record<StepDecisionKind, string>
const missing = "This alert no longer exists, or you can't see it any more."
const invalid = "Couldn't save the decision. Reload the page and try again."

/**
 * One decision on one runbook step (DOMAIN.md §6): the step moves to its next status at once (optimistic), goes back
 * when the API refuses, and the run reloads on a refusal, since a `409` means the step changed elsewhere. An accepted
 * decision also reloads the alert (an approved escalation adds teams) and its history (every decision is audited).
 */
export function useStepDecision(alertId: string, step: StepRunRead) {
  const me = useMe()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const runKey = getGetRunbookRunQueryKey(alertId)

  const updateStep = (next: StepRunRead) =>
    queryClient.setQueryData<getRunbookRunResponse>(runKey, (response) =>
      response?.status === 200 && response.data !== null
        ? {
            ...response,
            data: {
              ...response.data,
              steps: response.data.steps.map((item) => (item.index === next.index ? next : item)),
            },
          }
        : response,
    )

  const fail = (message: string | null) => {
    updateStep(step)
    setError(message)
    void queryClient.invalidateQueries({ queryKey: runKey, exact: true })
  }

  const mutation = useDecideStep({
    mutation: {
      onMutate: ({ data }) => {
        setError(null)
        updateStep({
          ...step,
          status: statusAfterDecision[data.decision],
          decided_by: me.user.id,
          decided_at: new Date().toISOString(),
        })
      },
      onSuccess: (response, { data }) => {
        switch (response.status) {
          case 200:
            queryClient.setQueryData<getRunbookRunResponse>(runKey, {
              status: 200,
              data: response.data,
              headers: response.headers,
            })
            void queryClient.invalidateQueries({ queryKey: getGetAlertQueryKey(alertId), exact: true })
            void queryClient.invalidateQueries({ queryKey: getListAuditEntriesQueryKey() })
            toast.success(decided[data.decision])
            return
          case 401:
            return fail(null)
          case 403:
            return fail(forbidden[data.decision])
          case 404:
            return fail(missing)
          case 409:
            return fail(changed)
          case 400:
          case 422:
            return fail(invalid)
          default:
            return fail(unexpectedStatusMessage(response))
        }
      },
      onError: () => fail(offline),
    },
  })

  return {
    /** Sends `decision`; resolves once the API has answered, whatever it answered. */
    decide: (decision: StepDecisionKind) =>
      mutation.mutateAsync({ alertId, index: step.index, data: { decision } }).then(
        (response) => response.status === 200,
        () => false,
      ),
    pending: mutation.isPending,
    /** Inline message after a refused or failed decision; `null` otherwise. */
    error,
  }
}
