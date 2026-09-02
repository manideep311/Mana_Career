"use client";

import { useMemo } from "react";

import { useRouter, useSearchParams } from "next/navigation";

import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { AddJobDialog } from "@/components/jobs/AddJobDialog";
import { JobCard } from "@/components/jobs/JobCard";
import { JobFilters } from "@/components/jobs/JobFilters";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { JobQuery } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** Default page size — matches the API's own default `limit`. */
const PAGE_SIZE = 24;

/** Filter keys read straight off the URL as trimmed strings. */
const STRING_KEYS = [
  "q",
  "work_mode",
  "seniority",
  "location",
  "employment_type",
  "sort",
] as const;

/**
 * `/jobs` — the discovery grid. Every filter lives in the URL query string
 * (`<JobFilters>` owns the writes); this page just reads it into a `JobQuery`,
 * runs the list query, and pages through results by rewriting `offset`.
 */
export default function JobsPage() {
  const { api } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sp = searchParams.toString();

  const query = useMemo<JobQuery>(() => {
    const params = new URLSearchParams(sp);
    const next: JobQuery = {};
    for (const key of STRING_KEYS) {
      const value = params.get(key)?.trim();
      if (value) next[key] = value;
    }
    const salaryMin = Number(params.get("salary_min"));
    if (Number.isFinite(salaryMin) && salaryMin > 0) next.salary_min = salaryMin;
    const limit = Number(params.get("limit"));
    if (Number.isFinite(limit) && limit > 0) next.limit = limit;
    const offset = Number(params.get("offset"));
    next.offset = Number.isFinite(offset) && offset > 0 ? offset : 0;
    return next;
  }, [sp]);

  const jobsQuery = useQuery({
    queryKey: qk.jobsList({ ...query }),
    queryFn: () => api.jobs.list(query),
  });

  function goToOffset(nextOffset: number): void {
    const params = new URLSearchParams(sp);
    if (nextOffset > 0) params.set("offset", String(nextOffset));
    else params.delete("offset");
    const qs = params.toString();
    router.push(qs ? `/jobs?${qs}` : "/jobs");
  }

  function body() {
    if (jobsQuery.isPending) {
      return (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-40" />
          ))}
        </div>
      );
    }

    if (jobsQuery.isError) {
      return <ErrorState onRetry={() => void jobsQuery.refetch()} />;
    }

    const data = jobsQuery.data;
    if (data.items.length === 0) {
      return (
        <EmptyState
          title="No jobs match"
          description="Try clearing filters, or paste a job description to add one."
        />
      );
    }

    const pageLimit = data.limit || PAGE_SIZE;
    const offset = data.offset ?? 0;

    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-text-muted">
          {`${data.total} role${data.total === 1 ? "" : "s"}`}
        </p>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>

        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => goToOffset(Math.max(0, offset - pageLimit))}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={offset + data.items.length >= data.total}
            onClick={() => goToOffset(offset + pageLimit)}
          >
            Next
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-text">Jobs</h1>
          <p className="text-sm text-text-muted">
            Browse open roles, or paste a job description to track one of your
            own.
          </p>
        </div>
        <AddJobDialog />
      </header>

      <JobFilters />

      {body()}
    </div>
  );
}
