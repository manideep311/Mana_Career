import { Check } from "lucide-react";

import { PaperRocket } from "@/components/motion/PaperRocket";
import { cn } from "@/lib/cn";

/**
 * Honest progress for a real hand-off: the paper rocket, the stage we are
 * actually in (announced politely to screen readers), and the short list of
 * stages. Stages advance only when the server says so; there is no fake
 * percentage and no timer pretending to move.
 *
 * `current` is the index of the active stage; `current >= stages.length`
 * means every stage is done.
 */
export function LaunchProgress({
  stages,
  current,
  detail,
  className,
}: {
  stages: readonly string[];
  current: number;
  detail?: string | null;
  className?: string;
}) {
  const finished = current >= stages.length;
  const headline = finished ? stages[stages.length - 1] : stages[Math.max(0, current)];

  return (
    <div
      className={cn(
        "flex flex-col gap-5 rounded-[var(--radius)] border border-border bg-surface p-6 shadow-[var(--shadow-1)] sm:flex-row sm:items-center",
        className,
      )}
    >
      <PaperRocket size={72} />
      <div className="flex min-w-0 flex-col gap-3">
        <div role="status" aria-live="polite" className="flex flex-col gap-1">
          <p className="font-display text-xl text-text">{headline}</p>
          {detail ? <p className="text-sm text-text-muted">{detail}</p> : null}
        </div>
        <ol aria-label="Progress" className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs">
          {stages.map((label, i) => {
            const done = finished || i < current;
            const active = !finished && i === current;
            return (
              <li
                key={label}
                aria-current={active ? "step" : undefined}
                className={cn(
                  "flex items-center gap-1.5",
                  done || active ? "text-text" : "text-text-muted",
                )}
              >
                {done ? (
                  <Check data-testid="step-done" className="h-3.5 w-3.5 text-positive" aria-hidden />
                ) : (
                  <span
                    aria-hidden
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      active ? "bg-accent" : "bg-border",
                    )}
                  />
                )}
                {label.replace(/…$/, "")}
                <span className="sr-only">{done ? " (done)" : active ? " (in progress)" : ""}</span>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
