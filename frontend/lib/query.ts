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
  section: (s: Section) => ["profile", s] as const,
};
