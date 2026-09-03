"use client";

import Link from "next/link";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import type { EvalStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * `status` → pill classes. Semantic tokens only (see `app/globals.css`).
 *  - `passed`          → positive tint
 *  - `failed` / `error` → danger tint
 *  - `running`         → muted text on the neutral surface
 */
const STATUS_CLASS: Record<EvalStatus, string> = {
  passed: "bg-positive-soft text-positive",
  failed: "bg-danger-soft text-danger",
  error: "bg-danger-soft text-danger",
  running: "bg-surface-sunk text-text-muted",
};

function StatusPill({ status }: { status: EvalStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold capitalize",
        STATUS_CLASS[status],
      )}
    >
      {status}
    </span>
  );
}

/** Grid template shared by the header row and every run row. */
const ROW = "grid grid-cols-[1fr_auto_5rem_4rem_5rem_6rem_1fr] items-center gap-4";

/**
 * `/eval` — admin-only. Lists every recorded eval run (newest first, as the API
 * returns them) and a button to kick off a fresh retrieval suite. Each row links
 * to the run's detail page.
 */
export default function EvalPage() {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const runsQuery = useQuery({
    queryKey: qk.evalRuns({}),
    queryFn: () => api.eval.listRuns(),
  });

  const runMut = useMutation({
    mutationFn: () => api.eval.createRun("retrieval"),
    onSuccess: () => {
      toast({ title: "Retrieval eval started." });
      void queryClient.invalidateQueries({ queryKey: qk.evalRuns({}) });
    },
    onError: () => toast({ title: "Couldn't start the eval.", variant: "danger" }),
  });

  function body() {
    if (runsQuery.isPending) {
      return (
        <div className="flex justify-center py-10 text-text-muted">
          <Spinner />
        </div>
      );
    }

    if (runsQuery.isError) {
      return <ErrorState onRetry={() => void runsQuery.refetch()} />;
    }

    const items = runsQuery.data.items;
    if (items.length === 0) {
      return <p className="text-sm text-text-muted">No eval runs yet.</p>;
    }

    return (
      <div className="overflow-x-auto">
        <div className="min-w-[46rem]">
          <div
            className={cn(
              ROW,
              "border-b border-border px-3 py-2 text-xs font-medium uppercase tracking-wide text-text-muted",
            )}
          >
            <span>Suite</span>
            <span>Status</span>
            <span>Recall@10</span>
            <span>MRR</span>
            <span>nDCG@10</span>
            <span>Commit</span>
            <span>Started</span>
          </div>

          {items.map((run) => (
            <Link
              key={run.id}
              href={`/eval/${run.id}`}
              className={cn(
                ROW,
                "border-b border-border px-3 py-3 text-sm text-text transition-colors hover:bg-surface-sunk",
              )}
            >
              <span className="capitalize">{run.suite}</span>
              <StatusPill status={run.status} />
              <span className="tabular-nums">
                {run.metrics.recall_at_10?.toFixed(3) ?? "—"}
              </span>
              <span className="tabular-nums">
                {run.metrics.mrr?.toFixed(3) ?? "—"}
              </span>
              <span className="tabular-nums">
                {run.metrics.ndcg_at_10?.toFixed(3) ?? "—"}
              </span>
              <span className="font-mono text-xs text-text-muted">
                {run.git_sha.slice(0, 7)}
              </span>
              <span className="text-text-muted">
                {new Date(run.started_at).toLocaleString()}
              </span>
            </Link>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-text">Eval</h1>
          <p className="text-sm text-text-muted">
            Retrieval, generation, and matching suites — metrics per recorded run.
          </p>
        </div>
        <Button
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending}
        >
          Run retrieval suite
        </Button>
      </header>

      <Card>
        <CardBody className="text-text">{body()}</CardBody>
      </Card>
    </div>
  );
}
