import { Check } from "lucide-react";

import type { JourneyStage } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/**
 * Profile -> skills -> proof -> applications -> target role, as a quiet line of
 * stops. Each stop's state comes from real data (the server decides what
 * "done" means); the current stop is the one to work on.
 */
export function JourneyPath({ stages }: { stages: JourneyStage[] }) {
  return (
    <ol aria-label="Your journey" className="grid gap-4 sm:grid-cols-5 sm:gap-2">
      {stages.map((stage, i) => {
        const done = stage.status === "done";
        const current = stage.status === "current";
        return (
          <li
            key={stage.key}
            aria-current={current ? "step" : undefined}
            className="relative flex gap-3 sm:flex-col sm:gap-2"
          >
            {i < stages.length - 1 ? (
              <span
                aria-hidden
                className={cn(
                  "absolute left-3 top-7 h-[calc(100%-0.5rem)] w-px sm:left-7 sm:top-3 sm:h-px sm:w-[calc(100%-1rem)]",
                  done ? "bg-positive" : "bg-border",
                )}
              />
            ) : null}
            <span
              aria-hidden
              className={cn(
                "relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border bg-surface",
                done && "border-positive bg-positive text-accent-fg",
                current && "border-accent ring-4 ring-accent-soft",
                !done && !current && "border-border",
              )}
            >
              {done ? <Check className="h-3.5 w-3.5" /> : null}
              {current ? <span className="h-2 w-2 rounded-full bg-accent" /> : null}
            </span>
            <div className="flex flex-col gap-0.5">
              <span className={cn("text-sm font-medium", current || done ? "text-text" : "text-text-muted")}>
                {stage.label}
                <span className="sr-only">
                  {done ? " (done)" : current ? " (you are here)" : " (later)"}
                </span>
              </span>
              <span className="text-xs text-text-muted">{stage.detail}</span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
