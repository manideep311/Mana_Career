"use client";

import { useMemo, useState } from "react";

import Link from "next/link";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { KanbanBoard } from "@/components/applications/KanbanBoard";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import type { Application, ApplicationListResponse, ApplicationStatus } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

function BoardInner() {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [movingId, setMovingId] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: qk.applications({ limit: 100 }),
    queryFn: () => api.applications.list({ limit: 100 }),
  });

  const jobIds = useMemo(
    () => [...new Set((listQuery.data?.items ?? []).map((a) => a.job_id))],
    [listQuery.data],
  );
  const jobQueries = useQueries({
    queries: jobIds.map((id) => ({
      queryKey: qk.job(id),
      queryFn: () => api.jobs.get(id),
      staleTime: 5 * 60_000,
    })),
  });
  const jobs = useMemo(() => {
    const map: Record<string, { title: string; company: string }> = {};
    jobQueries.forEach((q, i) => {
      if (q.data) map[jobIds[i]] = { title: q.data.title ?? "", company: q.data.company ?? "" };
    });
    return map;
  }, [jobQueries, jobIds]);

  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ApplicationStatus }) =>
      api.applications.patch(id, { status }),
    onMutate: async ({ id, status }) => {
      setMovingId(id);
      const key = qk.applications({ limit: 100 });
      await queryClient.cancelQueries({ queryKey: key });
      const prev = queryClient.getQueryData<ApplicationListResponse>(key);
      if (prev) {
        queryClient.setQueryData<ApplicationListResponse>(key, {
          ...prev,
          items: prev.items.map((a) =>
            a.id === id
              ? { ...a, status, last_status_change_at: new Date().toISOString() }
              : a,
          ),
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(qk.applications({ limit: 100 }), ctx.prev);
      toast({ title: "Couldn't move that application.", variant: "danger" });
    },
    onSettled: (_d, _e, vars) => {
      setMovingId(null);
      // Mark the board stale without an immediate refetch: the optimistic write
      // already matches the row `patch` returned, and refetching now would race
      // the optimistic frame. It refreshes on the next mount/focus.
      void queryClient.invalidateQueries({
        queryKey: qk.applications({ limit: 100 }),
        refetchType: "none",
      });
      void queryClient.invalidateQueries({ queryKey: qk.application(vars.id) });
    },
  });

  if (listQuery.isPending) {
    return (
      <div className="flex gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-64 w-72 shrink-0" />
        ))}
      </div>
    );
  }
  if (listQuery.isError) {
    return <ErrorState title="We couldn't load your applications." onRetry={() => listQuery.refetch()} />;
  }

  const items: Application[] = listQuery.data.items;
  if (items.length === 0) {
    return (
      <EmptyState
        title="No applications yet"
        description="Save a job to start tracking it, or prepare one with Mana AI."
        action={
          <Link href="/jobs" className={buttonVariants({ variant: "default" })}>
            Browse jobs
          </Link>
        }
      />
    );
  }

  return (
    <KanbanBoard
      applications={items}
      jobs={jobs}
      movingId={movingId}
      onMove={(id, status) => move.mutate({ id, status })}
    />
  );
}

export default function ApplicationsPage() {
  return (
    <RequireAuth>
      <div className="space-y-6">
        <header>
          <h1 className="text-xl font-semibold text-text">Applications</h1>
          <p className="text-sm text-text-muted">Every role you&apos;re tracking, by stage.</p>
        </header>
        <BoardInner />
      </div>
    </RequireAuth>
  );
}
