"use client";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import type { SkillGap, SkillMention } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/**
 * Severity → chip classes / labels. Copied verbatim from
 * `components/jobs/SkillGaps.tsx` (module-local there, not exported): semantic
 * tokens only, the same vocabulary `MatchBadge` uses.
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

/**
 * The two side-by-side panels at the top of the Insights page: what the user is
 * already strong at, and the aggregate skill gaps rolled up from their job
 * matches. The Refresh button re-runs the roll-up (hence `"use client"`).
 */
export function SkillPanels({
  strengths,
  gaps,
  onRefresh,
  refreshing,
}: {
  strengths: SkillMention[];
  gaps: SkillGap[];
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardBody className="flex flex-col gap-3 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-subtle">
            Strengths
          </p>
          {strengths.length === 0 ? (
            <p className="text-sm text-text-muted">
              No standout strengths yet — keep scoring jobs.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {strengths.map((s) => (
                <li key={s.skill_slug} className="flex flex-col">
                  <span className="text-sm font-medium text-text">
                    {s.skill_label}
                  </span>
                  {s.detail ? (
                    <span className="text-xs text-text-muted">{s.detail}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardBody className="flex flex-col gap-3 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-medium uppercase tracking-wide text-text-subtle">
              Skills to develop
            </p>
            <Button
              variant="outline"
              size="sm"
              loading={refreshing}
              onClick={onRefresh}
            >
              Refresh
            </Button>
          </div>
          {gaps.length === 0 ? (
            <p className="text-sm text-text-muted">
              No gaps rolled up yet — Refresh to compute them from your job
              matches.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {gaps.map((g) => (
                <li key={g.id} className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                      SEVERITY_CLASS[g.severity],
                    )}
                  >
                    {SEVERITY_LABEL[g.severity]}
                  </span>
                  <span className="text-sm font-medium text-text">
                    {g.skill_label}
                  </span>
                  {g.rationale ? (
                    <span className="text-xs italic text-text-muted">
                      {g.rationale}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
