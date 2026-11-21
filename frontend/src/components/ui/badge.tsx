import { mergeProps } from '@base-ui/react/merge-props'
import { useRender } from '@base-ui/react/use-render'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

/** Class names for each Badge variant. */
const badgeVariants = cva(
  'inline-flex h-5 w-fit shrink-0 items-center gap-1 rounded-full px-2 text-[12px]/[16px] font-medium whitespace-nowrap [&>svg]:pointer-events-none [&>svg]:size-3.5',
  {
    variants: {
      variant: {
        neutral: 'bg-muted text-muted-foreground',
        tint: 'bg-c-tint text-c-text',
      },
    },
    defaultVariants: {
      variant: 'neutral',
    },
  },
)

/** Small pill for counts, roles and severities; always full radius (DESIGN.md §7). */
export function Badge({
  className,
  variant,
  render,
  ...props
}: useRender.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: 'span',
    props: mergeProps<'span'>({ className: cn(badgeVariants({ variant }), className) }, props),
    render,
    state: { slot: 'badge', variant },
  })
}
