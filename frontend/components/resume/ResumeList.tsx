"use client";

import { FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import type { ResumeOut, ResumeStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/** Human labels for the pipeline statuses that aren't `"failed"` / `"extracted"`. */
const PROGRESS_LABELS: Record<
  Exclude<ResumeStatus, "failed" | "extracted">,
  string
> = {
  uploaded: "Uploaded",
  parsing: "Reading your résumé",
  parsed: "Parsed",
  extracting: "Understanding the details",
};

/** A short, human status line for one résumé row. */
function statusLabel(resume: ResumeOut): string {
  if (resume.status === "failed") return "Couldn't process";
  if (resume.status === "extracted") {
    return resume.confirmed_at ? "Confirmed" : "Ready to review";
  }
  return PROGRESS_LABELS[resume.status];
}

const CONFIRM_DELETE =
  "Delete this résumé? Any profile data built from it stays, but the file and its extraction are removed.";

/**
 * The résumé list shown on `/resume` to a returning user who already has a
 * confirmed résumé: re-review an extraction, retry a failed parse, switch which
 * résumé is primary, delete one, or upload another.
 *
 * Purely presentational — every side effect is a callback prop. The row whose
 * `id` matches `busyId` renders its buttons `disabled` while the parent runs a
 * mutation for it. Delete is guarded by `window.confirm`, so `onDelete` only
 * fires when the user accepts.
 */
export function ResumeList({
  resumes,
  onSetPrimary,
  onReview,
  onRetry,
  onDelete,
  onUploadAnother,
  busyId,
}: {
  resumes: ResumeOut[];
  onSetPrimary: (id: string) => void;
  onReview: (id: string) => void;
  onRetry: (id: string) => void;
  onDelete: (id: string) => void;
  onUploadAnother: () => void;
  busyId: string | null;
}) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardBody className="p-0">
          <ul className="divide-y divide-border">
            {resumes.map((resume) => {
              const busy = resume.id === busyId;
              const canReview =
                resume.status === "extracted" && !resume.confirmed_at;
              const displayName =
                resume.title ?? resume.original_filename ?? "Résumé";

              return (
                <li
                  key={resume.id}
                  className={cn(
                    "flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between",
                    busy && "opacity-60",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <FileText
                      className="mt-0.5 h-5 w-5 shrink-0 text-text-muted"
                      aria-hidden
                    />
                    <div className="flex flex-col gap-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-text">
                          {displayName}
                        </span>
                        {resume.is_primary ? (
                          <span className="rounded-full border border-accent px-2 py-0.5 text-xs font-medium text-accent">
                            Primary
                          </span>
                        ) : null}
                      </div>
                      <span className="text-xs text-text-muted">
                        {statusLabel(resume)} &middot; Uploaded{" "}
                        {new Date(resume.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {canReview ? (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        aria-label={`Re-review ${displayName}`}
                        onClick={() => onReview(resume.id)}
                      >
                        Review
                      </Button>
                    ) : null}
                    {resume.status === "failed" ? (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        aria-label={`Retry ${displayName}`}
                        onClick={() => onRetry(resume.id)}
                      >
                        Try again
                      </Button>
                    ) : null}
                    {resume.is_primary ? null : (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        aria-label={`Make ${displayName} primary`}
                        onClick={() => onSetPrimary(resume.id)}
                      >
                        Make primary
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={busy}
                      aria-label={`Delete ${displayName}`}
                      onClick={() => {
                        if (window.confirm(CONFIRM_DELETE)) {
                          onDelete(resume.id);
                        }
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </CardBody>
      </Card>

      <div>
        <Button variant="outline" onClick={onUploadAnother}>
          Upload another résumé
        </Button>
      </div>
    </div>
  );
}
