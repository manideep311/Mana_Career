import { QueryClient, defaultShouldDehydrateQuery } from "@tanstack/react-query";
import type { Section } from "@/lib/api/types";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
      },
      dehydrate: {
        shouldDehydrateQuery: (query) =>
          defaultShouldDehydrateQuery(query) ||
          (query.state.status === "pending"),
      },
    },
  });
}

export const qk = {
  profile: ["profile"] as const,
  strength: ["profile", "strength"] as const,
  skills: ["profile", "skills"] as const,
  section: (s: Section) => ["profile", s] as const,
  resumes: ["resumes"] as const,
  resumeExtraction: (id: string | null) => ["resume", id, "extraction"] as const,
  jobs: ["jobs"] as const,
  jobsList: (q: Record<string, unknown>) => ["jobs", "list", q] as const,
  job: (id: string) => ["jobs", id] as const,
  match: (jobId: string) => ["match", jobId] as const,
  matchList: (q: Record<string, unknown>) => ["match", "list", q] as const,
  skillGaps: (jobMatchId: string) => ["skill-gaps", jobMatchId] as const,
  evalRuns: (q: Record<string, unknown>) => ["eval", "runs", q] as const,
  evalRun: (id: string) => ["eval", "run", id] as const,
  evalResults: (id: string) => ["eval", "results", id] as const,
};
