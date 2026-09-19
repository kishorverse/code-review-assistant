import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from 'cn'
import { Slot } from 'radix-ui'

const buttonVariants = cva(
  "relative inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 overflow-hidden rounded-control border font-medium whitespace-nowrap transition-[background-color,border-color,color,box-shadow,transform] duration-200 ease-out-expo outline-none select-none active:scale-[0.97] disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:transition-transform [&_svg]:duration-300 [&_svg:not([class*='size-'])]:size-3.5",
  {
    variants: {
      variant: {
        primary:
          'group/btn border-transparent bg-[linear-gradient(135deg,var(--color-accent),var(--color-accent-2))] text-on-accent shadow-[0_1px_0_rgb(255_255_255/0.18)_inset,0_1px_2px_rgb(0_0_0/0.12),0_6px_16px_-6px_color-mix(in_srgb,var(--color-accent)_60%,transparent)] hover:shadow-glow hover:[&_svg:last-child]:translate-x-0.5 after:absolute after:inset-0 after:-translate-x-full after:bg-[linear-gradient(100deg,transparent_20%,rgb(255_255_255/0.28)_50%,transparent_80%)] after:transition-transform after:duration-700 after:ease-out-expo hover:after:translate-x-full',
        secondary:
          'border-line bg-surface text-text shadow-[0_1px_2px_rgb(0_0_0/0.04)] hover:border-line-strong hover:bg-subtle',
        ghost: 'border-transparent text-muted hover:bg-hover hover:text-text',
        danger: 'border-line bg-surface text-critical hover:border-critical/40 hover:bg-critical/5',
      },
      size: {
        sm: 'h-7 px-2.5 text-[12.5px]',
        md: 'h-8 px-3 text-[13px]',
        lg: 'h-10 px-4.5 text-[13.5px]',
        icon: 'size-8',
      },
    },
    defaultVariants: {
      variant: 'secondary',
      size: 'md',
    },
  },
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : 'button'
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />
}

export { Button, buttonVariants }
