"use client";

import { useMemo } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorState } from "@/components/common/ErrorState";
import { Card, CardBody } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import type { AiAction } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const STATUS_CLASS: Record<AiAction["status"], string> = {
  ok: "bg-positive-soft text-positive",
  warning: "bg-warning-soft text-warning",
  error: "bg-danger-soft text-danger",
};

function rel(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export default function ActivityPage() {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const query = useQuery({
    queryKey: qk.aiActions({}),
    queryFn: () => api.ai.listActions({ limit: 100 }),
  });

  const rerun = useMutation({
    mutationFn: (sessionId: string) =>
      api.ai.startGoal(sessionId, { goal: "understand_job", inputs: {} }),
    onSuccess: () => {
      toast({ title: "Re-running…" });
      void queryClient.invalidateQueries({ queryKey: qk.aiActions({}) });
    },
    onError: () => toast({ title: "Couldn’t start the run.", variant: "danger" }),
  });

  const groups = useMemo(() => {
    const items = query.data?.items ?? [];
    const bySession = new Map<string, AiAction[]>();
    for (const a of items) {
      const key = a.ai_session_id ?? "—";
      const list = bySession.get(key) ?? [];
      list.push(a);
      bySession.set(key, list);
    }
    return [...bySession.entries()];
  }, [query.data]);

  function body() {
    if (query.isPending) {
      return (
        <div className="flex justify-center py-10 text-text-muted">
          <Spinner />
        </div>
      );
    }
    if (query.isError) {
      return <ErrorState onRetry={() => void query.refetch()} />;
    }
    if (groups.length === 0) {
      return <p className="text-sm text-text-muted">Nothing yet — ask Mana something.</p>;
    }
    return (
      <div className="flex flex-col gap-6">
        {groups.map(([sessionId, list]) => (
          <div key={sessionId} className="flex flex-col gap-2">
            {list.map((a) => (
              <div
                key={a.id}
                className="flex items-center gap-3 rounded-[var(--radius)] border border-border bg-surface px-3 py-2 text-sm"
              >
                <span className="font-mono text-xs text-text-muted">{a.node}</span>
                <span className="flex-1 text-text">{a.summary}</span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-semibold capitalize",
                    STATUS_CLASS[a.status],
                  )}
                >
                  {a.status}
                </span>
                <span className="text-xs text-text-muted">{rel(a.occurred_at)}</span>
                {a.status !== "ok" && a.ai_session_id ? (
                  <button
                    type="button"
                    onClick={() => rerun.mutate(a.ai_session_id as string)}
                    disabled={rerun.isPending}
                    className="text-xs font-medium text-accent underline-offset-4 hover:underline"
                  >
                    Try again
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-text">Activity</h1>
        <p className="text-sm text-text-muted">
          Everything Mana has done on your behalf, newest first.
        </p>
      </header>
      <Card>
        <CardBody className="text-text">{body()}</CardBody>
      </Card>
    </div>
  );
}
