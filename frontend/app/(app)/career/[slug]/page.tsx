"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import { FitChip } from "@/components/career/FitChip";
import { Section } from "@/components/career/Section";
import { SkillStepCard } from "@/components/career/SkillStepCard";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageBanner } from "@/components/common/PageBanner";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemError } from "@/lib/api/fetcher";
import type { CareerPath, PathAction, PathSkill } from "@/lib/api/types";
import { PAGE_ART } from "@/lib/page-art";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const linkCls = "font-medium text-accent underline-offset-4 hover:underline";

function actionHref(kind: PathAction["kind"]): string {
  switch (kind) {
    case "project":
      return "#skills";
    case "resume":
      return "/resume#review";
    case "apply":
      return "#roles";
    case "roadmap":
      return "/insights#roadmap";
    default:
      return "/career";
  }
}

function roleShare(skill: PathSkill, jobs: number): string {
  const n = Math.max(1, Math.round(skill.demand * jobs));
  return `asked for in ${n} of ${jobs} role${jobs === 1 ? "" : "s"}`;
}

function Have({ path }: { path: CareerPath }) {
  if (path.have.length === 0) {
    return (
      <p className="text-sm text-text-muted">
        None of the core skills for these roles are on your profile yet. That&apos;s a
        starting point, not a verdict.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {path.have.map((s) => (
        <li key={s.slug} className="rounded-[var(--radius)] border border-border bg-surface p-3 text-sm">
          <span className="font-semibold text-text">{s.label}</span>
          <span className="text-text-muted"> · {roleShare(s, path.job_count)}</span>
          {s.evidence.length > 0 ? (
            <blockquote className="mt-1 border-l-2 border-positive/50 pl-3 text-text-muted">
              {s.evidence[0]}
            </blockquote>
          ) : (
            <p className="mt-1 text-xs text-text-muted">
              Listed on your profile; no résumé line shows it in use yet.
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

function Missing({ path }: { path: CareerPath }) {
  if (path.missing.length === 0) {
    return <p className="text-sm text-text-muted">You cover every core skill we track for these roles.</p>;
  }
  return (
    <ul className="flex flex-wrap gap-2">
      {path.missing.map((s) => (
        <li
          key={s.slug}
          className="rounded-full border border-border bg-surface px-3 py-1 text-sm text-text"
          title={roleShare(s, path.job_count)}
        >
          {s.label}
          <span className="text-xs text-text-muted">
            {" "}
            · {s.required ? "usually required" : "a plus"}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function CareerPathPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug ?? "";
  const { api } = useAuth();

  const pathQ = useQuery({
    queryKey: qk.careerPath(slug),
    queryFn: () => api.career.path(slug),
    retry: (count, err) => !(err instanceof ProblemError && err.status === 404) && count < 1,
  });
  const planQ = useQuery({
    queryKey: qk.careerSkills(slug),
    queryFn: () => api.career.skills(slug),
    enabled: pathQ.isSuccess,
  });

  const back = (
    <Link href="/career" className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text">
      <ArrowLeft className="h-4 w-4" aria-hidden />
      All paths
    </Link>
  );

  if (pathQ.isPending) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading path">
        {back}
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (pathQ.isError) {
    const notFound = pathQ.error instanceof ProblemError && pathQ.error.status === 404;
    return (
      <div className="flex flex-col gap-6">
        {back}
        {notFound ? (
          <EmptyState
            art={PAGE_ART.notFound}
            title="We couldn't find that path"
            description="It may no longer match the roles we know about."
            action={
              <Link href="/career" className={buttonVariants()}>
                See your paths
              </Link>
            }
          />
        ) : (
          <ErrorState title="We couldn't load this path." onRetry={() => void pathQ.refetch()} />
        )}
      </div>
    );
  }

  const path = pathQ.data;
  return (
    <article className="flex flex-col gap-10">
      <div className="flex flex-col gap-3">
        {back}
        <PageBanner
          art={PAGE_ART.careerPath}
          title={path.title}
          badge={<FitChip fit={path.fit} label={path.fit_label} />}
          description={path.summary || undefined}
        />
      </div>

      <Section id="why" title="Why this path">
        <p className="text-base leading-relaxed text-text">{path.why}</p>
        {path.relevant_experience.length > 0 ? (
          <p className="text-sm text-text-muted">
            Related roles you&apos;ve held: {path.relevant_experience.join(", ")}.
          </p>
        ) : null}
        {path.evidence_is_thin ? (
          <p className="text-sm text-warning">
            We know only a few of your skills, so treat this as a rough read.
          </p>
        ) : null}
      </Section>

      <Section id="have" title="What you already have">
        <Have path={path} />
      </Section>

      <Section id="missing" title="What's missing">
        <Missing path={path} />
      </Section>

      <Section id="difficulty" title="How big a move this is">
        <p className="text-sm text-text">
          <span className="font-semibold">{path.fit_label}.</span> {path.fit_explanation}
        </p>
        {path.seniority_note ? <p className="text-sm text-text-muted">{path.seniority_note}</p> : null}
      </Section>

      {path.next_actions.length > 0 ? (
        <Section id="next" title="Next steps">
          <ol className="flex flex-col gap-2">
            {path.next_actions.map((a) => (
              <li key={a.title} className="rounded-[var(--radius)] border border-border bg-surface p-4 text-sm">
                <Link href={actionHref(a.kind)} className={linkCls}>
                  {a.title}
                </Link>
                <p className="mt-1 text-text-muted">{a.detail}</p>
              </li>
            ))}
          </ol>
        </Section>
      ) : null}

      <Section id="skills" title="Skills to build first" intro="The few that matter most for this path, each with a way to prove it.">
        {planQ.isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : planQ.isError || !planQ.data ? (
          <ErrorState title="We couldn't load the skill plan." onRetry={() => void planQ.refetch()} />
        ) : planQ.data.steps.length === 0 ? (
          <p className="text-sm text-text-muted">Nothing to add: you already cover the core skills.</p>
        ) : (
          <ol className="flex flex-col gap-3">
            {planQ.data.steps.map((step, i) => (
              <SkillStepCard key={step.slug} step={step} index={i} />
            ))}
          </ol>
        )}
      </Section>

      <Section id="roles" title="Roles behind this path">
        {path.roles.length === 0 ? (
          <p className="text-sm text-text-muted">No open roles in this family right now.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {path.roles.map((r) => (
              <li key={r.id}>
                <Link href={`/jobs/${r.id}`} className={linkCls}>
                  {r.title}
                </Link>
                {r.company ? <span className="text-sm text-text-muted"> · {r.company}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {path.related.length > 0 ? (
        <Section id="related" title="Also worth a look">
          <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
            {path.related.map((r) => (
              <li key={r.slug}>
                <Link href={`/career/${r.slug}`} className={linkCls}>
                  {r.title}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </article>
  );
}
