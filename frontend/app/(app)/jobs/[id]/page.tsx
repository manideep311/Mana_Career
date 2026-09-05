"use client";

import { useEffect } from "react";

import { useParams, useRouter } from "next/navigation";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorState } from "@/components/common/ErrorState";
import { fmtSalary } from "@/components/jobs/JobCard";
import { WhyThisMatch } from "@/components/jobs/WhyThisMatch";
import { TailorButton } from "@/components/resume/TailorButton";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import { useJobEvents } from "@/hooks/useJobEvents";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** Same pill styling the discovery `<JobCard>` uses for its meta chips. */
const CHIP_CLASS =
  "rounded-full border border-border px-2 py-0.5 text-xs capitalize text-text-muted";

/**
 * `/jobs/[id]` — one posting in full.
 *
 * While the ingest pipeline is still running (`status === "ingesting"`) this
 * shows a small "we're reading this posting" panel wired to the same SSE stream
 * the Add-a-job flow uses, and swaps itself for the real layout once the stream
 * reports `ready`. The ready layout is the JD proper plus the Phase 5 match
 * breakdown (`<WhyThisMatch>`) and a placeholder for the Phase 8 Prepare
 * Application flow.
 */
export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";

  const { api } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const jobQuery = useQuery({
    queryKey: qk.job(id),
    queryFn: () => api.jobs.get(id),
  });

  const job = jobQuery.data;
  const ingesting = job?.status === "ingesting";

  const ev = useJobEvents(ingesting ? id : null);

  useEffect(() => {
    if (ev.status === "ready") {
      void queryClient.invalidateQueries({ queryKey: qk.job(id) });
    }
  }, [ev.status, queryClient, id]);

  const removeMut = useMutation({
    mutationFn: () => api.jobs.remove(id),
    onSuccess: () => {
      toast({ title: "Removed." });
      void queryClient.invalidateQueries({ queryKey: qk.jobs });
      router.push("/jobs");
    },
    onError: () =>
      toast({ title: "Couldn't remove that job.", variant: "danger" }),
  });

  if (jobQuery.isPending) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (jobQuery.isError || !job) {
    return <ErrorState onRetry={() => void jobQuery.refetch()} />;
  }

  if (job.status === "ingesting") {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <Card>
          <CardBody className="flex flex-col gap-1">
            <p className="text-sm font-medium text-text">
              We&apos;re reading this posting…
            </p>
            <p className="text-sm text-text-muted">
              {ev.message ?? "This can take a moment."}
            </p>
          </CardBody>
        </Card>
      </div>
    );
  }

  const title = job.title || "Untitled role";
  const metaLine = [job.company, job.location].filter(Boolean).join(" · ");
  const chips = [job.work_mode, job.seniority, job.employment_type].filter(
    (v): v is string => Boolean(v),
  );
  const salary = fmtSalary(job);
  const experienceLine =
    job.experience_min_years != null
      ? job.experience_max_years != null
        ? `${job.experience_min_years}–${job.experience_max_years} years`
        : `${job.experience_min_years}+ years`
      : null;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
      <header className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h1 className="text-2xl font-semibold text-text">{title}</h1>
            {metaLine ? (
              <p className="text-sm text-text-muted">{metaLine}</p>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {job.is_seed ? (
              <span className="rounded-full bg-surface-sunk px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-text-muted">
                Sample
              </span>
            ) : null}
            {job.is_seed === false ? (
              <Button
                variant="ghost"
                size="sm"
                loading={removeMut.isPending}
                onClick={() => removeMut.mutate()}
              >
                Remove
              </Button>
            ) : null}
          </div>
        </div>

        {chips.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {chips.map((chip) => (
              <span key={chip} className={CHIP_CLASS}>
                {chip}
              </span>
            ))}
          </div>
        ) : null}

        {salary ? (
          <p className="text-sm font-medium text-text">{salary}</p>
        ) : null}
      </header>

      <WhyThisMatch jobId={id} />

      <TailorButton jobId={id} />

      <div className="flex flex-col gap-6">
        {job.description ? (
          <p className="whitespace-pre-line text-sm text-text">
            {job.description}
          </p>
        ) : null}

        {job.responsibilities.length > 0 ? (
          <section className="flex flex-col gap-2">
            <h2 className="text-base font-semibold text-text">
              Responsibilities
            </h2>
            <ul className="list-disc pl-5 text-sm text-text-muted">
              {job.responsibilities.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {job.required_skills.length > 0 ? (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-text">Required skills</h3>
            <div className="flex flex-wrap gap-1.5">
              {job.required_skills.map((skill) => (
                <span key={skill.slug} className={CHIP_CLASS}>
                  {skill.label}
                </span>
              ))}
            </div>
          </section>
        ) : null}

        {job.preferred_skills.length > 0 ? (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-text">Preferred skills</h3>
            <div className="flex flex-wrap gap-1.5">
              {job.preferred_skills.map((skill) => (
                <span key={skill.slug} className={CHIP_CLASS}>
                  {skill.label}
                </span>
              ))}
            </div>
          </section>
        ) : null}

        {experienceLine ? (
          <p className="text-sm text-text-muted">
            <span className="font-semibold text-text">Experience:</span>{" "}
            {experienceLine}
          </p>
        ) : null}

        <details className="text-sm text-text-muted">
          <summary className="cursor-pointer text-text">Original posting</summary>
          <pre className="mt-2 whitespace-pre-wrap rounded-[var(--radius)] bg-surface-sunk p-4 text-xs text-text-muted">
            {job.raw_text}
          </pre>
        </details>
      </div>
    </div>
  );
}
