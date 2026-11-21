import type { CSSProperties } from 'react'
import { CircleCheck, CircleX, Info, LoaderCircle, TriangleAlert } from 'lucide-react'
import { Toaster as Sonner, type ToasterProps } from 'sonner'
import { useResolvedTheme } from '@/hooks/use-resolved-theme'
import { layers } from '@/lib/layers'

const iconProps = { size: 16, strokeWidth: 1.75, 'aria-hidden': true } as const

const toasterStyle = {
  zIndex: layers.toast,
  '--normal-bg': 'var(--popover)',
  '--normal-text': 'var(--popover-foreground)',
  '--normal-border': 'var(--border)',
  '--width': '360px',
} as const satisfies CSSProperties & Record<`--${string}`, string>

/** Toast stack for transient confirmations: bottom right, one at a time, 4 s (DESIGN.md §9). */
export function Toaster(props: ToasterProps) {
  const theme = useResolvedTheme()
  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      visibleToasts={1}
      duration={4000}
      style={toasterStyle}
      icons={{
        success: <CircleCheck {...iconProps} />,
        info: <Info {...iconProps} />,
        warning: <TriangleAlert {...iconProps} />,
        error: <CircleX {...iconProps} />,
        loading: <LoaderCircle {...iconProps} className="animate-spin" />,
      }}
      toastOptions={{ classNames: { toast: 'rounded-xl! shadow-popover! font-sans text-[14px]/[20px]' } }}
      {...props}
    />
  )
}
