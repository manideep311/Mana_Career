import { forwardRef, type ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const Textarea = forwardRef<HTMLTextAreaElement, ComponentProps<"textarea">>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "min-h-20 w-full rounded-[var(--radius)] border border-border bg-surface px-3 py-2 text-sm text-text outline-none placeholder:text-text-subtle focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
        "aria-[invalid=true]:border-danger aria-[invalid=true]:ring-[color-mix(in_srgb,var(--danger)_45%,transparent)]",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
