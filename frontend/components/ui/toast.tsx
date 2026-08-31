"use client";

import * as ToastPrimitive from "@radix-ui/react-toast";
import { forwardRef, type ComponentProps } from "react";

import { cn } from "@/lib/cn";

export type ToastVariant = "default" | "danger";

export const ToastRoot = forwardRef<
  HTMLLIElement,
  ComponentProps<typeof ToastPrimitive.Root> & { variant?: ToastVariant }
>(({ className, variant = "default", ...props }, ref) => (
  <ToastPrimitive.Root
    ref={ref}
    className={cn(
      "flex items-start gap-3 rounded-[var(--radius)] border bg-surface p-4 shadow-[var(--shadow-2)]",
      variant === "danger" ? "border-danger" : "border-border",
      className,
    )}
    {...props}
  />
));
ToastRoot.displayName = "ToastRoot";

export const ToastTitle = forwardRef<
  HTMLDivElement,
  ComponentProps<typeof ToastPrimitive.Title>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Title
    ref={ref}
    className={cn("text-sm font-semibold text-text", className)}
    {...props}
  />
));
ToastTitle.displayName = "ToastTitle";

export const ToastDescription = forwardRef<
  HTMLDivElement,
  ComponentProps<typeof ToastPrimitive.Description>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Description
    ref={ref}
    className={cn("mt-1 text-sm text-text-muted", className)}
    {...props}
  />
));
ToastDescription.displayName = "ToastDescription";

export const ToastClose = forwardRef<
  HTMLButtonElement,
  ComponentProps<typeof ToastPrimitive.Close>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Close
    ref={ref}
    className={cn(
      "-m-1 rounded-[var(--radius)] p-1 text-text-subtle transition-colors hover:text-text focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:outline-none",
      className,
    )}
    {...props}
  />
));
ToastClose.displayName = "ToastClose";
