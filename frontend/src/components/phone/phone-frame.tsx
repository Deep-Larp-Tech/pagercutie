import type { ReactNode } from 'react'

/** Props for `PhoneFrame`. */
export interface PhoneFrameProps {
  /** Accessible name of the device, e.g. "Simulated phone". */
  label: string
  /** Fixed content at the top of the screen: title and filters. */
  header: ReactNode
  /** Scrolling content of the screen. */
  children: ReactNode
}

/**
 * Rounded device outline, centred and at most 380 px wide, that marks its content as a simulated phone (ADR-0013).
 * The screen scrolls inside the frame, so the page keeps its height.
 */
export function PhoneFrame({ label, header, children }: PhoneFrameProps) {
  return (
    <section
      aria-label={label}
      className="mx-auto w-full max-w-[380px] rounded-[44px] border bg-card p-2.5 shadow-card"
    >
      <div className="flex h-[clamp(480px,calc(100svh-220px),720px)] flex-col overflow-hidden rounded-[36px] border bg-background">
        <div className="flex justify-center pt-2.5 pb-1" aria-hidden>
          <span className="h-1.5 w-16 rounded-full bg-muted" />
        </div>
        <div className="flex flex-col gap-3 border-b px-4 pt-2 pb-3">{header}</div>
        <div className="flex-1 overflow-y-auto px-3 py-3">{children}</div>
      </div>
    </section>
  )
}
