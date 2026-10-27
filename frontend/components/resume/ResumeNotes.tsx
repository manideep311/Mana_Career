"use client";

import { useQuery } from "@tanstack/react-query";
import { Info, ShieldAlert } from "lucide-react";

import type { AppMeta } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

function useMeta(): AppMeta | undefined {
  const { api } = useAuth();
  return useQuery({
    queryKey: qk.meta,
    queryFn: () => api.meta.get(),
    staleTime: Infinity,
    retry: false,
  }).data;
}

/**
 * Under the upload box on a public demo: a résumé is personal data, so say
 * what happens to it before anyone picks a file.
 */
export function UploadPrivacyNote() {
  const m = useMeta();
  if (!m || (!m.demo_mode && m.retention_days <= 0)) return null;
  return (
    <p role="note" className="flex items-start gap-2 text-xs text-text-muted">
      <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>
        Demo: don&apos;t upload a résumé with details you want kept private.
        {m.retention_days > 0
          ? ` Accounts and their files are deleted ${m.retention_days} days after sign-up.`
          : ""}
      </span>
    </p>
  );
}

/**
 * Above the review form when no AI model reads résumés here: explains why
 * experience and education are empty instead of letting it look broken.
 */
export function NoAiReaderNote() {
  const m = useMeta();
  if (!m || m.ai_writing) return null;
  return (
    <p
      role="note"
      className="mb-4 flex items-start gap-2 rounded-[var(--radius)] border border-border bg-surface-sunk px-3 py-2 text-xs text-text-muted"
    >
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>
        No AI reader runs here, so only skills, your email and profile links were picked up
        from the text. Add experience and education on your Profile after confirming.
      </span>
    </p>
  );
}
