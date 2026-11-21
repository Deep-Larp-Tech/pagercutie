import { Button as ButtonPrimitive } from '@base-ui/react/button'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import { controlTransition, focusRing } from './styles'

/** Class names for each Button variant and size (DESIGN.md §9). */
const buttonVariants = cva(
  [
    'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-transparent font-medium whitespace-nowrap select-none',
    'active:scale-97 disabled:pointer-events-none disabled:opacity-50',
    '[&_svg]:pointer-events-none [&_svg]:shrink-0',
    controlTransition,
    focusRing,
  ],
  {
    variants: {
      variant: {
        primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
        secondary:
          'border-border bg-secondary text-secondary-foreground hover:bg-accent aria-expanded:bg-accent',
        ghost: 'text-foreground hover:bg-accent aria-expanded:bg-accent',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
      },
      size: {
        sm: 'h-7 px-2.5 text-[12px]/[16px] [&_svg]:size-3.5',
        md: 'h-8 px-3 text-[14px]/[20px] [&_svg]:size-4',
        'icon-sm': 'size-7 [&_svg]:size-3.5',
        'icon-md': 'size-8 [&_svg]:size-4',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
)

/** Button with a verb label; icon sizes take an icon and an `aria-label` instead. */
export function Button({
  className,
  variant,
  size,
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
}
