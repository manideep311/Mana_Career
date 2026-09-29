"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { PathCard } from "@/components/career/PathCard";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * `/career` — the role families your experience points toward, each with the
 * evidence behind it. Suggestions to weigh, not verdicts.
 */
export default function CareerPathsPage() {
  const { api } = useAuth();
  const paths = useQuery({ queryKey: qk.careerPaths, queryFn: () => api.career.paths() });

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-display text-3xl text-text">Where your experience could take you</h1>
        <p className="text-sm text-text-muted">
          These paths appear relevant based on the skills in your résumé and profile, compared
          with the roles we know about. Open one to see why, what you already have, and
          what&apos;s missing.
        </p>
      </header>

      {paths.isPending ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading paths">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : paths.isError || !paths.data ? (
        <ErrorState title="We couldn't load your paths." onRetry={() => void paths.refetch()} />
      ) : paths.data.paths.length === 0 ? (
        <EmptyState
          title="No paths to suggest yet"
          description="Upload your résumé or add the tools you use to your profile, and we'll map the roles they point to."
          action={
            <Link href="/resume" className={buttonVariants()}>
              Upload your résumé
            </Link>
          }
        />
      ) : (
        <>
          <ul className="flex flex-col gap-3">
            {paths.data.paths.map((p) => (
              <PathCard key={p.slug} path={p} />
            ))}
          </ul>
          {paths.data.notes.length > 0 ? (
            <aside className="flex flex-col gap-1 border-l-2 border-border pl-4 text-sm text-text-muted">
              {paths.data.notes.map((n) => (
                <p key={n}>{n}</p>
              ))}
            </aside>
          ) : null}
        </>
      )}
    </div>
  );
}
