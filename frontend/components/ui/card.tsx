import type { ComponentProps, ComponentPropsWithoutRef } from "react";

import { cn } from "@/lib/cn";

export function Card({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius)] border border-border bg-surface shadow-[var(--shadow-1)]",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn("flex flex-col gap-1 p-5 pb-0", className)}
      {...props}
    />
  );
}

export function CardTitle({
  as: Tag = "h2",
  className,
  ...props
}: ComponentPropsWithoutRef<"h2"> & { as?: "h2" | "h3" }) {
  return (
    <Tag
      className={cn("text-base font-semibold text-text", className)}
      {...props}
    />
  );
}

export function CardBody({ className, ...props }: ComponentProps<"div">) {
  return (
    <div className={cn("p-5 text-sm text-text-muted", className)} {...props} />
  );
}

export function CardFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 border-t border-border p-5",
        className,
      )}
      {...props}
    />
  );
}
