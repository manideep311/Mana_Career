"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { FitChip } from "@/components/career/FitChip";
import { Section } from "@/components/career/Section";
import { SkillStepCard } from "@/components/career/SkillStepCard";
import { ErrorState } from "@/components/common/ErrorState";
import { JourneyPath } from "@/components/dashboard/JourneyPath";
import { NextActions } from "@/components/dashboard/NextActions";
import { WelcomeBanner } from "@/components/dashboard/WelcomeBanner";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { CareerOverview } from "@/lib/api/types";
import { BAND_LABEL } from "@/lib/match";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

function partOfDay(now: Date = new Date()): "morning" | "afternoon" | "evening" {
  const hour = now.getHours();
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

const linkCls = "text-sm font-medium text-accent underline-offset-4 hover:underline";

function Direction({ o }: { o: CareerOverview }) {
  const d = o.direction;
  return (
    <Card className="animate-rise">
      <CardBody className="flex flex-col gap-3 p-6">
        <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
          Your direction
        </p>
        {d ? (
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-display text-2xl text-text">{d.title}</h2>
            <FitChip fit={d.fit} label={d.fit_label} />
          </div>
        ) : null}
        <p className="text-base leading-relaxed text-text">{o.direction_summary}</p>
        {d ? (
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            <Link href={`/career/${d.slug}`} className={linkCls}>
              Why this path, and what&apos;s missing
            </Link>
            <Link href="/career" className={linkCls}>
              Compare other paths
            </Link>
          </div>
        ) : o.has_resume ? (
          <Link href="/profile" className={buttonVariants({ variant: "outline", className: "self-start" })}>
            Add the tools you use
          </Link>
        ) : (
          <Link href="/resume" className={buttonVariants({ className: "self-start" })}>
            Upload your résumé
          </Link>
        )}
      </CardBody>
    </Card>
  );
}

function Roadmap({ o }: { o: CareerOverview }) {
  const r = o.roadmap;
  if (!r) {
    return (
      <p className="text-sm text-text-muted">
        No roadmap yet.{" "}
        <Link href="/insights#roadmap" className={linkCls}>
          Turn your skill gaps into a plan
        </Link>
      </p>
    );
  }
  return (
    <Card>
      <CardBody className="flex flex-col gap-2">
        <p className="text-sm text-text-muted">
          {r.title} · {r.done} of {r.total} steps done
        </p>
        {r.current ? (
          <p className="text-base font-semibold text-text">
            {r.current.status === "in_progress" ? "Working on: " : "Up next: "}
            {r.current.title}
          </p>
        ) : (
          <p className="text-base font-semibold text-text">Every step is done. Nice work.</p>
        )}
        {r.upcoming ? (
          <p className="text-sm text-text-muted">Then: {r.upcoming.title}</p>
        ) : null}
        <Link href="/insights#roadmap" className={linkCls}>
          Open your roadmap
        </Link>
      </CardBody>
    </Card>
  );
}

function Opportunities({ o }: { o: CareerOverview }) {
  if (o.opportunities.length === 0) {
    return (
      <p className="text-sm text-text-muted">
        No close matches scored yet.{" "}
        <Link href="/jobs" className={linkCls}>
          Browse roles and score a few against your profile
        </Link>
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {o.opportunities.map((job) => (
        <li key={job.job_id}>
          <Link
            href={`/jobs/${job.job_id}`}
            className="flex flex-col gap-1 rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-1)] transition-colors hover:border-accent/40"
          >
            <span className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm font-semibold text-text">
                {job.title}
                {job.company ? <span className="font-normal text-text-muted"> · {job.company}</span> : null}
              </span>
              {job.band ? (
                <span className="text-xs font-medium text-positive">{BAND_LABEL[job.band]}</span>
              ) : null}
            </span>
            <span className="text-xs text-text-muted">
              {[job.reason, job.gap].filter(Boolean).join(" · ")}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function DashboardPage() {
  const { user, api } = useAuth();
  const firstName = user?.full_name?.split(" ")[0] ?? "there";

  const overview = useQuery({
    queryKey: qk.careerOverview,
    queryFn: () => api.career.overview(),
  });
  const o = overview.data;

  return (
    <div className="flex flex-col gap-10">
      <WelcomeBanner
        title={`Good ${partOfDay()}, ${firstName}`}
        subtitle="Where you are, where you could go, and the next useful step."
      />

      {overview.isPending ? (
        <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading your overview">
          <Skeleton className="h-36 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : overview.isError || !o ? (
        <ErrorState
          title="We couldn't load your overview."
          onRetry={() => void overview.refetch()}
        />
      ) : (
        <>
          <Direction o={o} />

          {o.next_actions.length > 0 ? (
            <Section id="next" title="What to do next">
              <NextActions actions={o.next_actions} />
            </Section>
          ) : null}

          <Section id="journey" title="Your journey">
            <JourneyPath stages={o.journey} />
          </Section>

          <Section id="roadmap" title="Your roadmap">
            <Roadmap o={o} />
          </Section>

          <Section id="opportunities" title="Roles that fit">
            <Opportunities o={o} />
          </Section>

          {o.skills.length > 0 && o.direction ? (
            <Section
              id="skills"
              title="Skills to build"
              action={
                <Link href={`/career/${o.direction.slug}#skills`} className={linkCls}>
                  Full plan
                </Link>
              }
            >
              <ol className="flex flex-col gap-2">
                {o.skills.map((step, i) => (
                  <SkillStepCard key={step.slug} step={step} index={i} compact />
                ))}
              </ol>
            </Section>
          ) : null}

          {o.notes.length > 0 ? (
            <aside className="flex flex-col gap-1 border-l-2 border-border pl-4 text-sm text-text-muted">
              {o.notes.map((note) => (
                <p key={note}>{note}</p>
              ))}
            </aside>
          ) : null}
        </>
      )}
    </div>
  );
}
