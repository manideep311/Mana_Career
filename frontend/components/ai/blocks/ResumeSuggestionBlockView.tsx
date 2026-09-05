"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { Spinner } from "@/components/ui/spinner";
import type { ResumeSuggestionBlock } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * `block.suggestion_id` is a `ResumeVersion` id (Phase 8a reused the
 * `resume_suggestion` stub kind to mean "a tailored version is ready" — see
 * the Phase 8b spec addendum §2). This view fetches that version and offers
 * a link to its diff page; there is no accept/edit/dismiss action to wire up
 * (no `resume_suggestions` API exists — the version is already-persisted
 * history, not a proposal needing disposal).
 */
export function ResumeSuggestionBlockView({ block }: { block: ResumeSuggestionBlock }) {
  const { api } = useAuth();

  const versionQuery = useQuery({
    queryKey: qk.resumeVersion(block.suggestion_id),
    queryFn: () => api.resumes.version(block.suggestion_id),
  });

  if (versionQuery.isPending) {
    return (
      <div className="flex justify-center rounded-[var(--radius)] border border-border bg-surface p-4 text-text-muted">
        <Spinner size="sm" />
      </div>
    );
  }
  if (versionQuery.isError) {
    return (
      <p className="rounded-[var(--radius)] border border-border bg-surface p-3 text-sm text-text-muted">
        Couldn’t load that résumé version.
      </p>
    );
  }

  const v = versionQuery.data;
  const cv = v.claim_validation;
  const groundedLine =
    cv.checked != null
      ? `${cv.checked - (cv.unsupported?.length ?? 0)} of ${cv.checked} claims grounded in your résumé`
      : null;

  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius)] border border-border bg-surface p-3">
      <p className="text-sm font-medium text-text">Your résumé was tailored for this role</p>
      {groundedLine ? <p className="text-xs text-text-muted">{groundedLine}</p> : null}
      <Link
        href={`/resume/versions/${v.id}`}
        className="text-sm font-medium text-accent underline-offset-4 hover:underline"
      >
        View changes
      </Link>
    </div>
  );
}
