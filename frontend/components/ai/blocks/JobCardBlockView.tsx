"use client";

import { useQuery } from "@tanstack/react-query";

import { JobCard } from "@/components/jobs/JobCard";
import { Spinner } from "@/components/ui/spinner";
import type { JobCard as JobCardT, JobCardBlock } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Fetches the referenced job and renders the standard `<JobCard>`. When the
 * block carries a `match_id`, the match is polled until it settles and the
 * score/band/status are threaded onto the card (mirrors the discovery grid).
 */
export function JobCardBlockView({ block }: { block: JobCardBlock }) {
  const { api } = useAuth();

  const jobQuery = useQuery({
    queryKey: qk.job(block.job_id),
    queryFn: () => api.jobs.get(block.job_id),
  });

  const matchQuery = useQuery({
    queryKey: qk.match(block.job_id),
    queryFn: () => api.matches.get(block.match_id as string),
    enabled: block.match_id != null,
    refetchInterval: (q) =>
      q.state.data && q.state.data.status === "scoring" ? 2000 : false,
  });

  if (jobQuery.isPending) {
    return (
      <div className="flex justify-center rounded-[var(--radius)] border border-border bg-surface p-4 text-text-muted">
        <Spinner size="sm" />
      </div>
    );
  }
  if (jobQuery.isError) {
    return (
      <p className="rounded-[var(--radius)] border border-border bg-surface p-3 text-sm text-text-muted">
        Couldn’t load this role.
      </p>
    );
  }

  const m = matchQuery.data;
  const job: JobCardT = {
    ...jobQuery.data,
    match_score: m?.score ?? jobQuery.data.match_score,
    match_band: m?.band ?? jobQuery.data.match_band,
    match_status: m?.status ?? jobQuery.data.match_status,
  };
  return <JobCard job={job} />;
}
