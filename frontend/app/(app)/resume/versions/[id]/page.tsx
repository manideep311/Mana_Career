"use client";

import { useState } from "react";

import { useParams } from "next/navigation";

import { useQuery } from "@tanstack/react-query";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { ErrorState } from "@/components/common/ErrorState";
import { VersionDiff } from "@/components/resume/VersionDiff";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import { ProblemError } from "@/lib/api/fetcher";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const FORMATS = [
  { fmt: "md" as const, label: "Markdown" },
  { fmt: "html" as const, label: "HTML" },
  { fmt: "pdf" as const, label: "PDF" },
  { fmt: "docx" as const, label: "DOCX" },
];

/** `/resume/versions/[id]` — the field-level diff for one tailored résumé version. */
export default function ResumeVersionPage() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";
  const { api, authedStream } = useAuth();
  const { toast } = useToast();
  const [rendering, setRendering] = useState<string | null>(null);

  const versionQuery = useQuery({
    queryKey: qk.resumeVersion(id),
    queryFn: () => api.resumes.version(id),
  });
  const diffQuery = useQuery({
    queryKey: qk.resumeDiff(id),
    queryFn: () => api.resumes.diff(id),
    enabled: versionQuery.isSuccess,
  });

  async function onRender(fmt: "md" | "html" | "pdf" | "docx") {
    setRendering(fmt);
    try {
      const res = await authedStream(api.resumes.renderUrl(id, fmt));
      if (res.status === 409) {
        toast({ title: "That format isn't available right now — try Markdown or HTML." });
        return;
      }
      if (!res.ok) throw new Error(`render ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      if (fmt === "docx") {
        const a = document.createElement("a");
        a.href = url;
        a.download = `resume.${fmt}`;
        a.click();
      } else {
        window.open(url, "_blank");
      }
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch {
      toast({ title: "Couldn't render that format.", variant: "danger" });
    } finally {
      setRendering(null);
    }
  }

  if (versionQuery.isPending) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (versionQuery.isError) {
    const notFound =
      versionQuery.error instanceof ProblemError && versionQuery.error.status === 404;
    return notFound ? (
      <p className="mx-auto w-full max-w-3xl text-sm text-text-muted">
        That résumé version wasn’t found.
      </p>
    ) : (
      <ErrorState onRetry={() => void versionQuery.refetch()} />
    );
  }

  return (
    <RequireAuth>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-text">
            {versionQuery.data.label ?? "Tailored résumé"}
          </h1>
          <p className="text-sm text-text-muted">
            Changes from your base résumé, {new Date(versionQuery.data.created_at).toLocaleString()}.
          </p>
        </header>

        <div className="flex flex-wrap gap-2">
          {FORMATS.map(({ fmt, label }) => (
            <Button
              key={fmt}
              variant="outline"
              size="sm"
              loading={rendering === fmt}
              onClick={() => void onRender(fmt)}
            >
              {label}
            </Button>
          ))}
        </div>

        {diffQuery.isPending ? (
          <Skeleton className="h-48 w-full" />
        ) : diffQuery.isError ? (
          <ErrorState onRetry={() => void diffQuery.refetch()} />
        ) : (
          <VersionDiff diff={diffQuery.data} claimValidation={versionQuery.data.claim_validation} />
        )}
      </div>
    </RequireAuth>
  );
}
