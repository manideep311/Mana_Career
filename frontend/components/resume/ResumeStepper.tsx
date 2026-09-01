import { Check, Loader2 } from "lucide-react";

import type { ResumeStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/**
 * The three visible stages of résumé processing, each mapped to the pipeline
 * statuses that make it the *active* stage. The backend also emits an `index`
 * stage — that lands in Phase 6, so it is deliberately absent here.
 */
const STEPS: { label: string; statuses: readonly ResumeStatus[] }[] = [
  { label: "Reading your résumé", statuses: ["uploaded", "parsing"] },
  { label: "Understanding the details", statuses: ["parsed", "extracting"] },
  { label: "Ready to review", statuses: ["extracted"] },
];

/**
 * Maps a résumé status to its 0-based step index: `-1` for `"failed"` (no step
 * is active), `0` for `null` or an unrecognised status.
 */
function stageIndex(status: ResumeStatus | null): number {
  if (status === "failed") return -1;
  if (status === null) return 0;
  const i = STEPS.findIndex((step) => step.statuses.includes(status));
  return i === -1 ? 0 : i;
}

/**
 * A three-step progress list for the résumé pipeline. The step matching
 * `status` shows a spinner (and `message` in place of its label when one is
 * set); earlier steps — and every step once `status` is `"extracted"` — show a
 * check; later steps show their 1-based number.
 *
 * Purely presentational: `status` / `message` come from `useResumeEvents`,
 * wired up by the `/resume` route.
 */
export function ResumeStepper({
  status,
  message,
}: {
  status: ResumeStatus | null;
  message: string | null;
}) {
  const active = stageIndex(status);
  const allDone = status === "extracted";

  return (
    <ol aria-live="polite" className="flex flex-col gap-3">
      {STEPS.map((step, i) => {
        const done = allDone || i < active;
        const isActive = !allDone && i === active;

        return (
          <li key={step.label} className="flex items-center gap-3 text-sm">
            <span
              className={cn(
                "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium",
                done && "border-accent bg-accent text-accent-fg",
                isActive && "border-accent text-accent",
                !done && !isActive && "border-border text-text-muted",
              )}
            >
              {done ? (
                <Check data-testid="step-done" className="h-4 w-4" aria-hidden />
              ) : isActive ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                i + 1
              )}
            </span>
            <span className={cn(done || isActive ? "text-text" : "text-text-muted")}>
              {isActive && message ? message : step.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
