"use client";

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";

import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Says plainly when the server runs in demo mode (sample providers, no real
 * model), so nobody mistakes template text for a finished draft. Silent when
 * the flag is off or the meta call fails.
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
  if (!m?.demo_mode) return null;
  const limits = [
    m.ai_writing
      ? null
      : "written drafts (cover letters, tailored résumés) use simple templates instead of a writing model",
    m.web_research ? null : "web research is off",
  ].filter(Boolean);
  return (
    <p
      role="note"
      className="mb-6 flex items-start gap-2 rounded-[var(--radius)] border border-border bg-surface-sunk px-3 py-2 text-xs text-text-muted"
    >
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>
        Demo mode. Career guidance is computed from your data as usual
        {limits.length > 0 ? `; ${limits.join(", and ")}` : ""}.
      </span>
    </p>
  );
}
