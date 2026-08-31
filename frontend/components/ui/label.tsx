import * as LabelPrimitive from "@radix-ui/react-label";
import { forwardRef, type ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const Label = forwardRef<
  HTMLLabelElement,
  ComponentProps<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn("text-sm font-medium text-text", className)}
    {...props}
  />
));
Label.displayName = "Label";
