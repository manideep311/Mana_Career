"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";

import { Section } from "@/components/career/Section";
import { ErrorState } from "@/components/common/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import type { AnalysisIssue, IssueSeverity, ResumeAnalysis } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const SEVERITY: Record<IssueSeverity, { label: string; cls: string; rank: number }> = {
  high: { label: "Fix first", cls: "bg-warning-soft text-warning", rank: 0 },
  medium: { label: "Worth a look", cls: "bg-accent-soft text-accent", rank: 1 },
  low: { label: "Polish", cls: "bg-surface-sunk text-text-muted", rank: 2 },
};

function Issue({ issue }: { issue: AnalysisIssue }) {
  const sev = SEVERITY[issue.severity];
  return (
    <li className="flex flex-col gap-3 rounded-[var(--radius)] border border-border bg-surface p-4 text-sm shadow-[var(--shadow-1)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-semibold text-text">{issue.problem}</p>
        <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-xs font-medium", sev.cls)}>
          {sev.label}
        </span>
      </div>
      <dl className="flex flex-col gap-2">
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Why it matters</dt>
          <dd className="text-text">{issue.why_it_matters}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Suggestion</dt>
          <dd className="text-text">{issue.suggestion}</dd>
        </div>
        {issue.examples.length > 0 ? (
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">From your résumé</dt>
            <dd className="flex flex-col gap-1">
              {issue.examples.map((ex) => (
                <q key={ex} className="border-l-2 border-border pl-3 text-text-muted">
                  {ex}
                </q>
              ))}
            </dd>
          </div>
        ) : null}
      </dl>
    </li>
  );
}

function Body({ a }: { a: ResumeAnalysis }) {
  const issues = [...a.issues].sort((x, y) => SEVERITY[x.severity].rank - SEVERITY[y.severity].rank);
  const applied = a.skills.filter((s) => s.applied);
  const listed = a.skills.filter((s) => !s.applied);

  return (
    <div className="flex flex-col gap-6">
      {a.enough_text ? (
        <p className="text-sm text-text-muted">
          {a.bullet_count} bullet point{a.bullet_count === 1 ? "" : "s"} ·{" "}
          {a.bullets_with_results} with a measurable result
          {a.page_count ? ` · ${a.page_count} page${a.page_count === 1 ? "" : "s"}` : ""}
          {a.target_path ? (
            <>
              {" "}· checked against{" "}
              <Link href={`/career/${a.target_path.slug}`} className="text-accent underline-offset-4 hover:underline">
                {a.target_path.title}
              </Link>{" "}
              roles
            </>
          ) : null}
        </p>
      ) : null}

      {a.strengths.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">What&apos;s working</h3>
          <ul className="flex flex-col gap-1.5">
            {a.strengths.map((s) => (
              <li key={s} className="flex gap-2 text-sm text-text">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-positive" aria-hidden />
                {s}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-text">What to improve</h3>
        {issues.length === 0 ? (
          <p className="text-sm text-text-muted">Nothing stands out. It reads clearly.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {issues.map((i) => (
              <Issue key={i.id} issue={i} />
            ))}
          </ul>
        )}
      </div>

      {a.skills.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Skills we found</h3>
          {applied.length > 0 ? (
            <p className="text-sm text-text">
              <span className="text-text-muted">Shown in your work: </span>
              {applied.map((s) => s.label).join(", ")}
            </p>
          ) : null}
          {listed.length > 0 ? (
            <p className="text-sm text-text">
              <span className="text-text-muted">Only listed, not shown in use: </span>
              {listed.map((s) => s.label).join(", ")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * How the résumé reads: what's working, then each issue as problem -> why it
 * matters -> suggestion, quoting the lines it's about. Everything comes from
 * the résumé text itself; missing skills are named as gaps, never as wording
 * to add.
 */
export function ResumeAnalysisPanel({ resumeId }: { resumeId: string }) {
  const { api } = useAuth();
  const q = useQuery({
    queryKey: qk.resumeAnalysis(resumeId),
    queryFn: () => api.resumes.analysis(resumeId),
  });

  return (
    <Section id="review" title="How your résumé reads">
      {q.isPending ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading résumé review">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : q.isError || !q.data ? (
        <ErrorState title="We couldn't review this résumé." onRetry={() => void q.refetch()} />
      ) : (
        <Body a={q.data} />
      )}
    </Section>
  );
}
