"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { JobMatch } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

export interface UseMatchResult {
  match: JobMatch | null;
  isLoading: boolean;
  refetch: () => void;
}

/**
 * On-demand job-match reader for the Job Detail page.
 *
 * `GET /matches/{id}` needs a match id, but a caller only has a `job_id`. So the
 * `queryFn` first `POST`s to `/matches` — `get_or_create` on the backend, safe
 * and cheap to call every run — and reads the row back by the id it returns.
 *
 * With `enabled` defaulting to `true`, merely mounting a component that calls
 * `useMatch(jobId)` requests the match (and kicks the scoring worker). While the
 * worker runs (`status === "scoring"`) the query re-polls every 2s; once the row
 * is `ready`/`failed` polling stops. `refetch()` invalidates the query to force
 * a fresh `create`→`get` pass (e.g. a manual "Score" / "Retry" button).
 */
export function useMatch(
  jobId: string | null,
  opts: { enabled?: boolean } = {},
): UseMatchResult {
  const { api } = useAuth();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: qk.match(jobId ?? ""),
    queryFn: async () => {
      const ref = await api.matches.create(jobId!);
      return api.matches.get(ref.id);
    },
    enabled: (opts.enabled ?? true) && !!jobId,
    refetchInterval: (q) => (q.state.data?.status === "scoring" ? 2000 : false),
  });

  return {
    match: query.data ?? null,
    isLoading: query.isPending,
    refetch: () => {
      void queryClient.invalidateQueries({ queryKey: qk.match(jobId ?? "") });
    },
  };
}
