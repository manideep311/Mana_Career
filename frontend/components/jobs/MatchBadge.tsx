"use client";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { MatchBand, MatchStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/**
 * Band → pill classes. Semantic tokens only — no raw hex or Tailwind color
 * literals (see `app/globals.css` `@theme inline`).
 *  - `strong`  → positive tint
 *  - `good`    → neutral sunk surface
 *  - `partial` → warning tint
 *  - `weak`    → muted text on the neutral surface
 */
const BAND_CLASS: Record<MatchBand, string> = {
  strong: "bg-positive-soft text-positive",
  good: "bg-surface-sunk text-text",
  partial: "bg-warning-soft text-warning",
  weak: "bg-surface-sunk text-text-muted",
};

/**
 * A tiny presentational read-out of one job match.
 *
 * Pure — it holds no state and never fetches. The Job Detail page drives it
 * from `useMatch`; a job *card* (Task 12) passes its own `match_*` fields in
 * with no `onScore` (read-only).
 *
 * States:
 *  - `ready` + a score → a band-colored score pill.
 *  - `scoring`         → "Scoring…" with a spinner.
 *  - `failed`          → "Score unavailable" (+ a "Retry" button when `onScore`).
 *  - `null`            → a "Score" button when `onScore` is given, else nothing.
 */
export function MatchBadge({
  score,
  band,
  status,
  onScore,
}: {
  score?: number | null;
  band?: MatchBand | null;
  status?: MatchStatus | null;
  onScore?: () => void;
}) {
  if (status === "ready" && score != null) {
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums",
          BAND_CLASS[band ?? "good"],
        )}
        title="Match score"
      >
        {String(Math.round(score))}
      </span>
    );
  }

  if (status === "scoring") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-text-muted">
        <Spinner size="sm" />
        Scoring…
      </span>
    );
  }

  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-text-muted">
        Score unavailable
        {onScore ? (
          <button
            type="button"
            onClick={onScore}
            className="font-medium text-accent underline-offset-4 hover:underline"
          >
            Retry
          </button>
        ) : null}
      </span>
    );
  }

  if (onScore) {
    return (
      <Button variant="outline" size="sm" onClick={onScore}>
        Score
      </Button>
    );
  }

  return null;
}
