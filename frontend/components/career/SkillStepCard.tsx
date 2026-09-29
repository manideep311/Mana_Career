import { ExternalLink } from "lucide-react";

import type { SkillStep } from "@/lib/api/types";

/**
 * One skill worth building next: why it matters for this path, what you
 * already have that relates, a concrete project to prove it, and (when the
 * catalogue has one) a resource to learn from. `compact` keeps the first two.
 */
export function SkillStepCard({
  step,
  index,
  compact = false,
}: {
  step: SkillStep;
  index: number;
  compact?: boolean;
}) {
  return (
    <li className="flex gap-4 rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-1)] animate-rise">
      <span
        aria-hidden
        className="font-display text-lg leading-6 text-text-muted tabular-nums"
      >
        {index + 1}
      </span>
      <div className="flex min-w-0 flex-col gap-2 text-sm">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="font-semibold text-text">{step.label}</h3>
          <span className="text-xs text-text-muted">{step.requirement}</span>
          {step.roadmap_position ? (
            <span className="text-xs text-accent">
              Step {step.roadmap_position} on your roadmap
            </span>
          ) : null}
        </div>
        <p className="text-text-muted">{step.why_it_matters}</p>
        {compact ? null : (
          <dl className="flex flex-col gap-2">
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">
                What you have
              </dt>
              <dd className="text-text">{step.current_evidence}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">
                Build this
              </dt>
              <dd className="text-text">{step.practice_project}</dd>
            </div>
            {step.resource ? (
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">
                  Learn from
                </dt>
                <dd>
                  <a
                    href={step.resource.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-accent underline-offset-4 hover:underline"
                  >
                    {step.resource.title}
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                    <span className="sr-only">(opens in a new tab)</span>
                  </a>
                  <span className="text-text-muted">
                    {" "}
                    · {step.resource.provider} · {step.resource.level}
                    {step.resource.est_hours ? ` · about ${step.resource.est_hours} h` : ""}
                    {` · ${step.resource.cost}`}
                  </span>
                </dd>
              </div>
            ) : null}
          </dl>
        )}
      </div>
    </li>
  );
}
