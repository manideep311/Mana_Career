import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ComponentProps } from "react";

import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/cn";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-[var(--radius)] text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] disabled:opacity-60 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        default: "bg-accent text-accent-fg shadow-[var(--shadow-1)] hover:brightness-95",
        outline: "border border-border bg-surface text-text hover:bg-surface-sunk",
        ghost: "text-text hover:bg-surface-sunk",
        danger: "bg-danger text-danger-fg hover:brightness-95",
        link: "text-accent underline-offset-4 hover:underline p-0 h-auto",
      },
      size: { sm: "h-8 px-3", md: "h-10 px-4", lg: "h-11 px-5", icon: "h-10 w-10" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { loading?: boolean };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <Spinner size="sm" /> : null}
      {children}
    </button>
  ),
);
Button.displayName = "Button";
