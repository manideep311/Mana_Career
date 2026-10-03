"use client";

import { useQuery } from "@tanstack/react-query";

import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Real numbers only: live counts from the catalogue the guidance draws on,
 * plus one promise the product enforces. No user counts, ratings or outcome
 * claims; if the counts can't load, only the promise shows.
 */
export function StatsStrip() {
  const { api } = useAuth();
  const stats = useQuery({
    queryKey: qk.catalogStats,
    queryFn: () => api.catalog.stats(),
    staleTime: 10 * 60_000,
    retry: false,
  });
  const s = stats.data;
  const items = s
    ? [
        { value: s.career_paths, label: "Career paths mapped from real roles" },
        { value: s.roles, label: "Roles analysed for the skills they ask for" },
        { value: s.skills, label: "Skills we can recognise in a résumé" },
      ].filter((i) => i.value > 0)
    : [];

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-medium text-text">Career guidance for every stage.</p>
      <dl className="flex flex-wrap gap-y-4 divide-border sm:divide-x">
        {stats.isPending
          ? [0, 1, 2].map((i) => (
              <div key={i} className="flex flex-col gap-1.5 pr-6 sm:px-6 sm:first:pl-0" aria-hidden>
                <span className="h-7 w-12 animate-pulse rounded bg-surface-sunk" />
                <span className="h-3 w-24 animate-pulse rounded bg-surface-sunk" />
              </div>
            ))
          : items.map((item) => (
              <div key={item.label} className="flex max-w-[10rem] flex-col gap-0.5 pr-6 sm:px-6 sm:first:pl-0">
                <dt className="order-2 text-xs leading-snug text-text-muted">{item.label}</dt>
                <dd className="order-1 font-display text-2xl text-accent tabular-nums">{item.value}</dd>
              </div>
            ))}
        <div className="flex max-w-[11rem] flex-col gap-0.5 pr-6 sm:px-6 sm:first:pl-0">
          <dt className="order-2 text-xs leading-snug text-text-muted">
            Nothing is sent without your approval.
          </dt>
          <dd className="order-1 font-display text-2xl text-accent">You decide</dd>
        </div>
      </dl>
    </div>
  );
}
