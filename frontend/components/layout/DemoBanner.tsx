"use client";

import { useQuery } from "@tanstack/react-query";
import { CirclePause, Info } from "lucide-react";

import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const NOTE =
  "mb-6 flex items-start gap-2 rounded-[var(--radius)] border border-border bg-surface-sunk px-3 py-2 text-xs text-text-muted";

/**
 * Says plainly when the server runs as a demo (and what that changes), and
 * when the day's free AI quota is used up, so nobody mistakes template text
 * for a finished draft or a paused feature for a broken one. Silent when
 * neither applies or the meta call fails.
 */
export function DemoBanner() {
  const { api } = useAuth();
  const meta = useQuery({
    queryKey: qk.meta,
    queryFn: () => api.meta.get(),
    staleTime: Infinity,
    retry: false,
  });
  const m = meta.data;
  if (!m) return null;
  const paused = m.ai_paused ? (
    <p role="note" className={NOTE}>
      <CirclePause className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>
        AI features are paused for today: the free daily quota is used up. Matching, career
        paths and skill plans still work.
      </span>
    </p>
  ) : null;
  if (!m.demo_mode) return paused;
  const limits = [
    m.ai_writing
      ? null
      : "written drafts (cover letters, tailored résumés) use simple templates instead of a writing model",
    m.web_research ? null : "web research is off",
    m.retention_days > 0
      ? `accounts are deleted ${m.retention_days} days after sign-up`
      : null,
  ].filter(Boolean);
  return (
    <>
      {paused}
      <p role="note" className={NOTE}>
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        <span>
          Demo mode. Career guidance is computed from your data as usual
          {limits.length > 0 ? `; ${limits.join(", and ")}` : ""}.
        </span>
      </p>
    </>
  );
}
