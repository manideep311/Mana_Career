import { forwardRef, type ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const Input = forwardRef<HTMLInputElement, ComponentProps<"input">>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-[var(--radius)] border border-border bg-surface px-3 text-sm text-text outline-none placeholder:text-text-subtle focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
        "aria-[invalid=true]:border-danger aria-[invalid=true]:ring-[color-mix(in_srgb,var(--danger)_45%,transparent)]",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
