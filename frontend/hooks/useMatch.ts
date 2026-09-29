"use client";

import { useEffect, useRef, useState } from "react";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { JobMatch } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

export interface UseMatchResult {
  match: JobMatch | null;
  isLoading: boolean;
  /** Scoring has run past the polling budget; polling has stopped. */
  stalled: boolean;
  refetch: () => void;
}

/** Poll quickly at first, back off, and give up after a budget. */
export const MATCH_POLL = { firstMs: 2_000, maxMs: 10_000, stepMs: 15_000, budgetMs: 180_000 };

export function nextPollDelay(elapsedMs: number): number {
  const doublings = Math.floor(elapsedMs / MATCH_POLL.stepMs);
  return Math.min(MATCH_POLL.maxMs, MATCH_POLL.firstMs * 2 ** doublings);
}

/**
 * On-demand job-match reader for the Job Detail page.
 *
 * `GET /matches/{id}` needs a match id, but a caller only has a `job_id`, so
 * the query first `POST`s to `/matches` (`get_or_create`, cheap and idempotent)
 * and reads the row back by the id it returns.
 *
 * While the worker scores (`status === "scoring"`) the query re-polls with
 * backoff (2 s, then 4 s, 8 s, capped at 10 s) and stops on `ready`/`failed`.
 * If scoring outlives `MATCH_POLL.budgetMs`, polling stops and `stalled` turns
 * true so the UI can offer a retry instead of spinning. (The server also fails
 * stuck jobs on its own, so a later refetch shows the real outcome.) Polling is
 * owned by TanStack Query and stops when the component unmounts.
 */
export function useMatch(
  jobId: string | null,
  opts: { enabled?: boolean } = {},
): UseMatchResult {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const scoringSince = useRef<number | null>(null);
  const [stalled, setStalled] = useState(false);

  const query = useQuery({
    queryKey: qk.match(jobId ?? ""),
    queryFn: async () => {
      if (!jobId) throw new Error("useMatch needs a job id");
      const ref = await api.matches.create(jobId);
      return api.matches.get(ref.id);
    },
    enabled: (opts.enabled ?? true) && !!jobId,
    refetchInterval: (q) => {
      if (q.state.data?.status !== "scoring" || stalled) return false;
      const since = scoringSince.current ?? Date.now();
      return nextPollDelay(Date.now() - since);
    },
  });

  const status = query.data?.status;
  useEffect(() => {
    if (status !== "scoring") {
      scoringSince.current = null;
      setStalled(false);
      return;
    }
    scoringSince.current ??= Date.now();
    const remaining = MATCH_POLL.budgetMs - (Date.now() - scoringSince.current);
    const timer = setTimeout(() => setStalled(true), Math.max(0, remaining));
    return () => clearTimeout(timer);
  }, [status]);

  return {
    match: query.data ?? null,
    isLoading: query.isPending,
    stalled,
    refetch: () => {
      scoringSince.current = null;
      setStalled(false);
      void queryClient.invalidateQueries({ queryKey: qk.match(jobId ?? "") });
    },
  };
}
