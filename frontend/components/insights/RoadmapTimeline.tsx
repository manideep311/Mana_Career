"use client";

import { useEffect, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { MilestoneRow } from "@/components/insights/MilestoneRow";
import { LaunchProgress } from "@/components/motion/LaunchProgress";
import { ErrorState } from "@/components/common/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import { useRoadmapEvents } from "@/hooks/useRoadmapEvents";
import type {
  Milestone,
  MilestonePhase,
  RoadmapDetail,
  RoadmapMilestoneStatus,
} from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const PHASES: { key: MilestonePhase; label: string }[] = [
  { key: "current", label: "Now" },
  { key: "next_30", label: "Next 30 days" },
  { key: "next_60_90", label: "Days 30 to 90" },
  { key: "later", label: "Later" },
  { key: "done", label: "Done" },
];

const PLANNING_STAGES = [
  "Looking at your skill gaps…",
  "Turning your goals into a practical next step…",
  "Your roadmap is ready",
];

/** "Roadmap for Senior Data Analyst" -> "Senior Data Analyst". */
function targetOf(title: string | undefined): string {
  const m = /^Roadmap for (.+)$/.exec(title ?? "");
  return m ? m[1] : "Your next role";
}

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

  const row = (m: Milestone) => (
    <MilestoneRow
      key={m.id}
      milestone={m}
      busy={movingId === m.id}
      onStatusChange={(s) => move.mutate({ id: m.id, status: s })}
    />
  );
  // Phases come from the server's timeline; live-streamed milestones don't
  // carry one yet, so they render as a plain ordered list until the refetch.
  const phased = milestones.length > 0 && milestones.every((m) => m.phase);
  const pace = roadmapQuery.data?.hours_per_week;

  return (
    <div className="flex flex-col gap-3">
      {events.status === "streaming" ? (
        <LaunchProgress
          stages={PLANNING_STAGES}
          current={milestones.length === 0 ? 0 : 1}
          detail={
            milestones.length > 0
              ? `${milestones.length} step${milestones.length === 1 ? "" : "s"} so far`
              : null
          }
        />
      ) : null}
      {milestones.length === 0 && events.status !== "streaming" ? (
        <p className="text-sm text-text-muted">
          No milestones yet. Your gaps may already be covered.
        </p>
      ) : phased ? (
        <div className="flex flex-col gap-5">
          {PHASES.map(({ key, label }) => {
            const inPhase = milestones.filter((m) => m.phase === key);
            if (inPhase.length === 0) return null;
            return (
              <section key={key} aria-label={label} className="flex flex-col gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                  {label}
                </h3>
                <ol className="flex flex-col gap-3">{inPhase.map(row)}</ol>
              </section>
            );
          })}
          <p className="flex flex-col gap-0.5 border-t border-border pt-3 text-sm">
            <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Target
            </span>
            <span className="text-text">{targetOf(roadmapQuery.data?.title)}</span>
          </p>
          {pace ? (
            <p className="text-xs text-text-muted">
              Timing assumes about {pace} hours a week. It&apos;s a guide, not a deadline.
            </p>
          ) : null}
        </div>
      ) : (
        <ol className="flex flex-col gap-3">{milestones.map(row)}</ol>
      )}
      {events.status === "error" && milestones.length === 0 ? (
        <ErrorState title={events.error ?? "We couldn't build your roadmap."} />
      ) : null}
    </div>
  );
}
