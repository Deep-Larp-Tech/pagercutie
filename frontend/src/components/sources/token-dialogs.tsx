import { useId, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { KeyRound } from 'lucide-react'
import type { SourceRead } from '@/api/generated/model'
import {
  getGetSourceQueryKey,
  getListSourcesQueryKey,
  rotateSourceToken,
  type rotateSourceTokenResponse,
} from '@/api/generated/sources/sources'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { CopyButton } from '@/components/ui/copy-button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { unexpectedStatusMessage } from '@/lib/api'
import { absoluteIngestUrl, ingestCommand } from '@/lib/ingest-example'
import { OFFLINE } from '@/lib/pagination'

/** Outcome of `POST /sources/{id}/token`: the new token, an error to show, or nothing (a `401` redirect). */
type RotateResult = { kind: 'token'; token: string } | { kind: 'failed'; message: string } | { kind: 'silent' }

function readRotate(response: rotateSourceTokenResponse | null): RotateResult {
  if (response === null) return { kind: 'failed', message: OFFLINE }
  switch (response.status) {
    case 200:
      return { kind: 'token', token: response.data.token }
    case 403:
      return { kind: 'failed', message: 'Only members and leads can change ingest tokens.' }
    case 404:
      return { kind: 'failed', message: 'This source no longer exists. Close this dialog to see the current list.' }
    case 422:
      return { kind: 'failed', message: "Couldn't change the token. Reload the page and try again." }
    case 401:
      return { kind: 'silent' }
    default:
      return { kind: 'failed', message: unexpectedStatusMessage(response) }
  }
}

/**
 * Requests a new token for a source. It calls the generated function directly instead of a TanStack mutation, so
 * the token lives only in the caller's state and never in the mutation cache or devtools (ADR-0072). A new token
 * reloads the source queries, which carry `has_token` and never the token.
 */
function useNewToken() {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  return {
    pending,
    request: async (sourceId: string): Promise<RotateResult> => {
      setPending(true)
      const response = await rotateSourceToken(sourceId).catch(() => null)
      setPending(false)
      const result = readRotate(response)
      if (result.kind === 'token') {
        void queryClient.invalidateQueries({ queryKey: getListSourcesQueryKey() })
        void queryClient.invalidateQueries({ queryKey: getGetSourceQueryKey(sourceId) })
      }
      return result
    },
  }
}

/** Props for `TokenReveal`. */
export interface TokenRevealProps {
  source: SourceRead
  token: string
}

/** A source's new token in a read-only field with a copy button, and a command that sends a test event (`NFR-4`). */
export function TokenReveal({ source, token }: TokenRevealProps) {
  const commandId = useId()
  const url = absoluteIngestUrl(source.ingest_url, window.location.origin)
  const command = ingestCommand(source.type, url, token)
  return (
    <div className="flex flex-col gap-4">
      <p role="status" className="flex items-center gap-2 font-medium">
        <KeyRound size={16} strokeWidth={1.75} aria-hidden className="text-primary" />
        This token is shown only once.
      </p>
      <p className="-mt-2 text-muted-foreground">Store it with the producer now. If it gets lost, rotate the token again.</p>
      <Field>
        <FieldLabel>Ingest token</FieldLabel>
        <div className="flex items-center gap-1">
          <Input
            readOnly
            value={token}
            spellCheck={false}
            autoComplete="off"
            className="font-mono text-[13px]"
            onFocus={(event) => event.currentTarget.select()}
          />
          <CopyButton value={token} label="Copy token" />
        </div>
      </Field>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between gap-2">
          <h3 id={commandId} className="text-[14px]/[20px] font-medium">
            Send a test event
          </h3>
          <CopyButton value={command} label="Copy command" />
        </div>
        <pre
          aria-labelledby={commandId}
          className="overflow-x-auto rounded-md bg-muted px-3 py-2 font-mono text-[13px]/[20px] whitespace-pre"
        >
          {command}
        </pre>
      </div>
    </div>
  )
}

/** Props for `RotateTokenDialog`. */
export interface RotateTokenDialogProps {
  /** The source whose token to replace; `null` closes the dialog. */
  source: SourceRead | null
  onClose: () => void
}

/**
 * Asks before replacing a source's ingest token (`POST /sources/{id}/token`), then shows the new token once. Closing
 * the dialog drops the token.
 */
export function RotateTokenDialog({ source, onClose }: RotateTokenDialogProps) {
  const newToken = useNewToken()
  const [token, setToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function close() {
    setToken(null)
    setError(null)
    onClose()
  }

  async function confirm(target: SourceRead) {
    setError(null)
    const result = await newToken.request(target.id)
    switch (result.kind) {
      case 'token':
        setToken(result.token)
        return
      case 'failed':
        setError(result.message)
        return
      case 'silent':
        return
      default:
        result satisfies never
    }
  }

  if (source !== null && token !== null) {
    return (
      <Dialog open onOpenChange={(open) => !open && close()}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>New token for {source.name}</DialogTitle>
            <DialogDescription>The old token no longer works.</DialogDescription>
          </DialogHeader>
          <TokenReveal source={source} token={token} />
          <DialogFooter>
            <DialogClose render={<Button />}>Done</DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <ConfirmDialog
      open={source !== null}
      onOpenChange={(open) => !open && close()}
      title={`Rotate the token for ${source?.name ?? 'this source'}?`}
      description="The current token stops working at once. Producers using it are rejected until they switch to the new one."
      confirmLabel="Rotate token"
      pendingLabel="Rotating…"
      pending={newToken.pending}
      error={error}
      onConfirm={() => source !== null && void confirm(source)}
    />
  )
}

/** Props for `FirstTokenStep`. */
export interface FirstTokenStepProps {
  /** A source without a token. */
  source: SourceRead
  /** Dialog title, e.g. "Payments webhook added". */
  title: string
  /** Closes the dialog; the token, if any, goes with it. */
  onDone: () => void
}

/**
 * Offers a source's first token (**Create token**), then shows it once. Used in the New source dialog after the
 * source is created and in `CreateTokenDialog`.
 */
export function FirstTokenStep({ source, title, onDone }: FirstTokenStepProps) {
  const newToken = useNewToken()
  const [token, setToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function create() {
    setError(null)
    const result = await newToken.request(source.id)
    switch (result.kind) {
      case 'token':
        setToken(result.token)
        return
      case 'failed':
        setError(result.message)
        return
      case 'silent':
        return
      default:
        result satisfies never
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>
          {token === null
            ? 'Producers need an ingest token to send events to it. Until then it rejects every event.'
            : 'Producers send events with this token.'}
        </DialogDescription>
      </DialogHeader>
      {token !== null && <TokenReveal source={source} token={token} />}
      {error !== null && (
        <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
          {error}
        </p>
      )}
      <DialogFooter>
        {token === null ? (
          <>
            <Button variant="secondary" onClick={onDone}>
              Close
            </Button>
            <Button disabled={newToken.pending} onClick={() => void create()}>
              {newToken.pending ? 'Creating…' : 'Create token'}
            </Button>
          </>
        ) : (
          <Button onClick={onDone}>Done</Button>
        )}
      </DialogFooter>
    </>
  )
}

/** Props for `CreateTokenDialog`. */
export interface CreateTokenDialogProps {
  /** A source without a token; `null` closes the dialog. */
  source: SourceRead | null
  onClose: () => void
}

/** Creates the first ingest token of a source from its row (`POST /sources/{id}/token`), then shows it once. */
export function CreateTokenDialog({ source, onClose }: CreateTokenDialogProps) {
  return (
    <Dialog open={source !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl">
        {source !== null && <FirstTokenStep key={source.id} source={source} title={`Token for ${source.name}`} onDone={onClose} />}
      </DialogContent>
    </Dialog>
  )
}
