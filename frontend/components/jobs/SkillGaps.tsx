"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Spinner } from "@/components/ui/spinner";
import type { SkillGap, SkillGapStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Severity → chip classes. Semantic tokens only (see `styles/tokens.css`),
 * the same vocabulary `MatchBadge` uses:
 *  - `critical`     → danger tint
 *  - `important`    → warning tint
 *  - `nice_to_have` → muted text on the neutral sunk surface
 */
const SEVERITY_CLASS: Record<SkillGap["severity"], string> = {
  critical: "bg-danger-soft text-danger",
  important: "bg-warning-soft text-warning",
  nice_to_have: "bg-surface-sunk text-text-muted",
};

const SEVERITY_LABEL: Record<SkillGap["severity"], string> = {
  critical: "Critical",
  important: "Important",
  nice_to_have: "Nice to have",
};

const STATUS_OPTIONS: SkillGapStatus[] = ["open", "learning", "closed"];

/**
 * The skill-gap list for one job match — rows of `severity → skill → rationale`
 * with a `<select>` that PATCHes each gap's status and refetches on success.
 *
 * `useQuery` + `useMutation` run on every render; the pending / empty / list
 * branches come after, so hook order stays stable.
 */
export function SkillGaps({ jobMatchId }: { jobMatchId: string }) {
  const { api } = useAuth();
  const queryClient = useQueryClient();

  const gapsQuery = useQuery({
    queryKey: qk.skillGaps(jobMatchId),
    queryFn: () => api.skillGaps.list(jobMatchId),
    enabled: !!jobMatchId,
  });

  const patchMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: SkillGapStatus }) =>
      api.skillGaps.patch(id, status),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: qk.skillGaps(jobMatchId) }),
  });

  if (gapsQuery.isPending) {
    return <Spinner />;
  }

  const gaps = gapsQuery.data ?? [];

  if (gaps.length === 0) {
    return (
      <p className="text-sm text-text-muted">
        No skill gaps — your profile covers this role.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {gaps.map((gap) => (
        <li
          key={gap.id}
          className="flex flex-wrap items-center gap-2 rounded-[var(--radius)] border border-border bg-surface p-2.5"
        >
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
              SEVERITY_CLASS[gap.severity],
            )}
          >
            {SEVERITY_LABEL[gap.severity]}
          </span>
          <span className="text-sm font-medium text-text">
            {gap.skill_label}
          </span>
          {gap.rationale ? (
            <span className="text-xs italic text-text-muted">
              {gap.rationale}
            </span>
          ) : null}
          <select
            aria-label={`Status for ${gap.skill_label}`}
            className="ml-auto rounded-[var(--radius)] border border-border bg-surface px-2 py-1 text-xs text-text"
            value={gap.status}
            disabled={patchMut.isPending}
            onChange={(e) =>
              patchMut.mutate({
                id: gap.id,
                status: e.target.value as SkillGapStatus,
              })
            }
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </li>
      ))}
    </ul>
  );
}
