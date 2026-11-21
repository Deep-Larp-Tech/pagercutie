import { Button } from '@/components/ui/button'
import type { ConnectionState } from '@/hooks/use-alert-stream'
import { layers } from '@/lib/layers'

/** Props for `ConnectionBar`. */
export interface ConnectionBarProps {
  connection: ConnectionState
  /** Reconnects now; offered once live updates are paused. */
  onRetry: () => void
}

/**
 * Live feed connection state (DESIGN.md §9 "Live connection"): nothing while connected, a thin "Reconnecting…" bar
 * under the header while the stream is reopened, "Live updates paused" with Retry after 10 s offline.
 */
export function ConnectionBar({ connection, onRetry }: ConnectionBarProps) {
  if (connection === 'connecting' || connection === 'connected') return null
  return (
    <div
      role="status"
      className="sticky top-14 flex min-h-8 items-center justify-between gap-3 rounded-md border bg-muted px-3 py-1 text-[12px]/[16px] font-medium text-muted-foreground"
      style={{ zIndex: layers.header }}
    >
      {connection === 'reconnecting' ? (
        <span>Reconnecting…</span>
      ) : (
        <>
          <span>Live updates paused</span>
          <Button size="sm" variant="secondary" onClick={onRetry}>
            Retry
          </Button>
        </>
      )}
    </div>
  )
}
