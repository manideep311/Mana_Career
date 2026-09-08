"use client";

import { useEffect, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { MilestoneRow } from "@/components/insights/MilestoneRow";
import { ErrorState } from "@/components/common/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import { useRoadmapEvents } from "@/hooks/useRoadmapEvents";
import type { Milestone, RoadmapDetail, RoadmapMilestoneStatus } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

export function RoadmapTimeline({
  recommendationId,
  live,
}: {
  recommendationId: string;
  live?: boolean;
}) {
  const { api } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [movingId, setMovingId] = useState<string | null>(null);

  const roadmapQuery = useQuery({
    queryKey: qk.roadmap(recommendationId),
    queryFn: () => api.roadmaps.get(recommendationId),
  });
  const streaming =
    !!live || roadmapQuery.data?.status === "planning";
  const events = useRoadmapEvents(streaming ? recommendationId : null);

  const { refetch } = roadmapQuery;
  useEffect(() => {
    if (events.status === "done") void refetch();
  }, [events.status, refetch]);

  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: RoadmapMilestoneStatus }) =>
      api.roadmaps.patchMilestone(recommendationId, id, status),
    onMutate: async ({ id, status }) => {
      setMovingId(id);
      const key = qk.roadmap(recommendationId);
      await queryClient.cancelQueries({ queryKey: key });
      const prev = queryClient.getQueryData<RoadmapDetail>(key);
      if (prev) {
        queryClient.setQueryData<RoadmapDetail>(key, {
          ...prev,
          milestones: prev.milestones.map((m) =>
            m.id === id ? { ...m, status } : m,
          ),
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(qk.roadmap(recommendationId), ctx.prev);
      toast({ title: "Couldn't update that milestone.", variant: "danger" });
    },
    onSettled: (_d, _e, vars) => {
      setMovingId(null);
      void queryClient.invalidateQueries({ queryKey: qk.roadmap(recommendationId) });
      if (vars.status === "done") {
        void queryClient.invalidateQueries({ queryKey: qk.insights });
      }
    },
  });

  const fromQuery = roadmapQuery.data?.milestones ?? [];
  const milestones: Milestone[] =
    events.milestones.length > fromQuery.length ? events.milestones : fromQuery;

  if (roadmapQuery.isPending && !live) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (roadmapQuery.isError && events.status === "idle") {
    return <ErrorState title="We couldn't load this roadmap." onRetry={() => void roadmapQuery.refetch()} />;
  }

  return (
    <div className="flex flex-col gap-3">
      {milestones.length === 0 && events.status !== "streaming" ? (
        <p className="text-sm text-text-muted">
          No milestones yet. Your gaps may already be covered.
        </p>
      ) : (
        <ol className="flex flex-col gap-3">
          {milestones.map((m) => (
            <MilestoneRow
              key={m.id}
              milestone={m}
              busy={movingId === m.id}
              onStatusChange={(s) => move.mutate({ id: m.id, status: s })}
            />
          ))}
        </ol>
      )}
      {events.status === "streaming" ? (
        <p className="flex items-center gap-2 text-xs text-text-muted">
          <Spinner size="sm" /> Building your roadmap…
        </p>
      ) : null}
      {events.status === "error" && milestones.length === 0 ? (
        <ErrorState title={events.error ?? "We couldn't build your roadmap."} />
      ) : null}
    </div>
  );
}
