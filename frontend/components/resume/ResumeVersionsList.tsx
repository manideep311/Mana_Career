"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { Skeleton } from "@/components/ui/skeleton";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** Newest-first list of a résumé's `ai_tailored` versions, each linking to its diff page. */
export function ResumeVersionsList({ resumeId }: { resumeId: string }) {
  const { api } = useAuth();
  const versionsQuery = useQuery({
    queryKey: qk.resumeVersions(resumeId),
    queryFn: () => api.resumes.versions(resumeId),
  });

  if (versionsQuery.isPending) {
    return <Skeleton className="h-16 w-full" />;
  }
  if (versionsQuery.isError) return null;

  const tailored = versionsQuery.data.items.filter((v) => v.kind === "ai_tailored");
  if (tailored.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-sm font-medium text-text">Tailored versions</h2>
      <ul className="flex flex-col gap-2">
        {tailored.map((v) => (
          <li key={v.id}>
            <Link
              href={`/resume/versions/${v.id}`}
              className="flex items-center justify-between rounded-[var(--radius)] border border-border bg-surface p-3 text-sm hover:bg-surface-sunk"
            >
              <span className="text-text">
                {v.label ?? `Tailored ${new Date(v.created_at).toLocaleDateString()}`}
              </span>
              <span className="text-accent">View changes</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
