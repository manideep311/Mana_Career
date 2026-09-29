import type { PathFit } from "@/lib/api/types";
import { cn } from "@/lib/cn";

const FIT_CLASS: Record<PathFit, string> = {
  close: "bg-positive-soft text-positive",
  stretch: "bg-accent-soft text-accent",
  pivot: "bg-surface-sunk text-text-muted",
};

/** Transition difficulty in words ("Reachable stretch"), never a probability. */
export function FitChip({ fit, label }: { fit: PathFit; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        FIT_CLASS[fit],
      )}
    >
      {label}
    </span>
  );
}
