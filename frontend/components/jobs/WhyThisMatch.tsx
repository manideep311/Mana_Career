"use client";

import { useQuery } from "@tanstack/react-query";

import { MatchBadge } from "@/components/jobs/MatchBadge";
import { SkillGaps } from "@/components/jobs/SkillGaps";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useMatch } from "@/hooks/useMatch";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** `"skill"` → `"Skill"`, `"nice_to_have"` → `"Nice To Have"`. */
function titleCase(value: string): string {
  return value
    .split(/[\s_]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** A dimension whose `raw_score` clears this reads as a ✓ rather than a △. */
const MET_THRESHOLD = 0.6;

/**
 * "Why this match" — the full read-out of one job match on the Job Detail page.
 *
 * `useMatch` plus the per-dimension `useQuery` are called on every render; the
 * five render states (loading / no-match / scoring / failed / ready) branch
 * only after both hooks have run, so hook order never shifts. The components
 * fetch is gated by `enabled` rather than by a conditional hook call.
 */
export function WhyThisMatch({ jobId }: { jobId: string }) {
  const { api } = useAuth();
  const { match, isLoading, refetch } = useMatch(jobId);

  const componentsQuery = useQuery({
    queryKey: [...qk.match(jobId), "components"],
    queryFn: () => api.matches.components(match?.id ?? ""),
    enabled: !!match && match.status === "ready",
  });

  if (isLoading) {
    return (
      <Card>
        <CardBody>
          <Spinner />
        </CardBody>
      </Card>
    );
  }

  if (match == null || match.status == null) {
    return (
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          <p>See how you match this role against your profile.</p>
          <Button type="button" onClick={refetch}>
            Score this job
          </Button>
        </CardBody>
      </Card>
    );
  }

  if (match.status === "scoring") {
    return (
      <Card>
        <CardBody className="flex items-center gap-2">
          <Spinner />
          <span>Scoring this role against your profile…</span>
        </CardBody>
      </Card>
    );
  }

  if (match.status === "failed") {
    return (
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          <p>{"We couldn't score this job."}</p>
          <Button type="button" onClick={refetch}>
            Try again
          </Button>
        </CardBody>
      </Card>
    );
  }

  // match.status === "ready"
  const components = componentsQuery.data ?? [];
  const strengths = match.strengths ?? [];

  return (
    <Card>
      <CardBody className="flex flex-col gap-4 text-text">
        {/* Fact: the score pill + band word + a plain-language anchor. */}
        <div className="flex flex-wrap items-center gap-2">
          <MatchBadge
            score={match.score}
            band={match.band}
            status={match.status}
          />
          {match.band ? (
            <span className="text-sm font-medium capitalize">{match.band}</span>
          ) : null}
          <span className="text-xs text-text-muted">
            vs. your current profile
          </span>
        </div>

        {/* Per-dimension breakdown — driven by GET /matches/{id}/components. */}
        <div className="flex flex-col gap-1.5">
          {componentsQuery.isPending ? (
            <Spinner size="sm" />
          ) : (
            components.map((component) => {
              const met = component.raw_score >= MET_THRESHOLD;
              return (
                <div
                  key={component.dimension}
                  className="flex items-center gap-2 text-sm"
                >
                  <span
                    aria-hidden
                    className={met ? "text-positive" : "text-text-muted"}
                  >
                    {met ? "✓" : "△"}
                  </span>
                  <span className="w-24 shrink-0">
                    {titleCase(component.dimension)}
                  </span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-sunk">
                    <span
                      className="block h-full rounded-full bg-accent"
                      style={{
                        width: `${Math.round(component.raw_score * 100)}%`,
                      }}
                    />
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* Strengths. */}
        {strengths.length > 0 ? (
          <p className="text-sm text-text-muted">
            {"You're strong on: " +
              strengths.map((strength) => strength.dimension).join(", ")}
          </p>
        ) : null}

        {/* Skill gaps. */}
        <SkillGaps jobMatchId={match.id} />

        {/* AI explanation — visually separated from the facts above (spec §7). */}
        <div className="rounded-[var(--radius)] border border-border bg-surface-sunk p-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-text-muted">
            {"Mana's read"}
          </p>
          <p className="text-sm text-text">
            {match.explanation ?? "No summary generated."}
          </p>
        </div>
      </CardBody>
    </Card>
  );
}
