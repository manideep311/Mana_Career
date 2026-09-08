"use client";

import { useState } from "react";

import { useMutation } from "@tanstack/react-query";

import { RoadmapTimeline } from "@/components/insights/RoadmapTimeline";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { useToast } from "@/components/ui/toaster";
import type { RoadmapSummary } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export function RoadmapSection({ summary }: { summary: RoadmapSummary | null }) {
  const { api } = useAuth();
  const { toast } = useToast();
  const [pendingId, setPendingId] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.roadmaps.create(),
    onSuccess: (ref) => setPendingId(ref.id),
    onError: () => toast({ title: "Couldn't start your roadmap.", variant: "danger" }),
  });

  return (
    <Card>
      <CardBody className="flex flex-col gap-4 p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-text">Learning roadmap</h2>
          {summary === null && pendingId === null ? (
            <Button size="sm" loading={create.isPending} onClick={() => create.mutate()}>
              Build my roadmap
            </Button>
          ) : null}
        </div>

        {pendingId !== null ? (
          <RoadmapTimeline recommendationId={pendingId} live />
        ) : summary !== null ? (
          <>
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium text-text">{summary.title}</p>
              <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunk">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{
                    width: `${
                      summary.milestones_total > 0
                        ? Math.round(
                            (summary.milestones_done / summary.milestones_total) * 100,
                          )
                        : 0
                    }%`,
                  }}
                />
              </div>
              <p className="text-xs text-text-muted">
                {summary.milestones_done} of {summary.milestones_total} done
                {summary.next_step ? ` · next: ${summary.next_step}` : ""}
              </p>
            </div>
            <RoadmapTimeline recommendationId={summary.id} />
          </>
        ) : (
          <p className="text-sm text-text-muted">
            No learning roadmap yet — build one from your top skill gaps.
          </p>
        )}
      </CardBody>
    </Card>
  );
}
