import { Button as ButtonPrimitive } from '@base-ui/react/button'
import type { VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import { buttonVariants } from './styles'

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
