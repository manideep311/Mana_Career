"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { NextStepCard } from "@/components/insights/NextStepCard";
import { RoadmapSection } from "@/components/insights/RoadmapSection";
import { SkillPanels } from "@/components/insights/SkillPanels";
import { TrendingAndProjects } from "@/components/insights/TrendingAndProjects";
import { ErrorState } from "@/components/common/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

export function InsightsView() {
  const { api } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const insights = useQuery({ queryKey: qk.insights, queryFn: () => api.insights.get() });

  const refresh = useMutation({
    mutationFn: () => api.skillGaps.aggregate(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.insights }),
    onError: () => toast({ title: "Couldn't refresh your skill gaps.", variant: "danger" }),
  });

  if (insights.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (insights.isError || !insights.data) {
    return <ErrorState title="We couldn't load your insights." onRetry={() => void insights.refetch()} />;
  }

  const d = insights.data;
  return (
    <div className="flex flex-col gap-6">
      <NextStepCard step={d.recommended_next_step} />
      <SkillPanels
        strengths={d.strengths}
        gaps={d.skills_to_develop}
        onRefresh={() => refresh.mutate()}
        refreshing={refresh.isPending}
      />
      <RoadmapSection summary={d.roadmap_summary} />
      <TrendingAndProjects trending={d.trending_skills} projects={d.suggested_projects} />
    </div>
  );
}
