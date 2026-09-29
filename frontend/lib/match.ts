import type { MatchBand } from "@/lib/api/types";

/** Words, not numbers, lead: the band says how close a role is. */
export const BAND_LABEL: Record<MatchBand, string> = {
  strong: "Strong match",
  good: "Good match",
  partial: "Partial match",
  weak: "Stretch",
};
