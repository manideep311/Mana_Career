"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { useQuery } from "@tanstack/react-query";

import { Card, CardBody } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import type { EvalStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** `status` → pill classes. Mirrors the listing page. */
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

/** Grid template shared by the results header row and every result row. */
const ROW = "grid grid-cols-[1fr_5rem_4rem_5rem_3rem] items-center gap-4";

/**
 * `/eval/[id]` — one eval run in full: a metrics header plus the per-case
 * results table.
 */
export default function EvalRunPage() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";

  const { api } = useAuth();

  const runQuery = useQuery({
    queryKey: qk.evalRun(id),
    queryFn: () => api.eval.getRun(id),
    enabled: !!id,
  });

  const resultsQuery = useQuery({
    queryKey: qk.evalResults(id),
    queryFn: () => api.eval.runResults(id),
    enabled: !!id,
  });

  const run = runQuery.data;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <Link href="/eval" className="text-sm text-text-muted hover:text-text">
        &larr; All runs
      </Link>

      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-text">
          {run ? `${run.suite} run` : "Eval run"}
        </h1>

        {run ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-text-muted">
            <StatusPill status={run.status} />
            <span>
              <span className="font-medium text-text">Provider:</span>{" "}
              {run.provider}
            </span>
            <span className="font-mono text-xs">{run.git_sha.slice(0, 7)}</span>
            <span className="tabular-nums">
              recall@10 {run.metrics.recall_at_10?.toFixed(3) ?? "—"}
            </span>
            <span className="tabular-nums">
              mrr {run.metrics.mrr?.toFixed(3) ?? "—"}
            </span>
            <span className="tabular-nums">
              ndcg@10 {run.metrics.ndcg_at_10?.toFixed(3) ?? "—"}
            </span>
          </div>
        ) : runQuery.isPending && !!id ? (
          <Spinner />
        ) : null}
      </header>

      <Card>
        <CardBody className="text-text">
          {resultsQuery.isPending && !!id ? (
            <div className="flex justify-center py-10 text-text-muted">
              <Spinner />
            </div>
          ) : !resultsQuery.data || resultsQuery.data.length === 0 ? (
            <p className="text-sm text-text-muted">No results for this run.</p>
          ) : (
            <div className="overflow-x-auto">
              <div className="min-w-[34rem]">
                <div
                  className={cn(
                    ROW,
                    "border-b border-border px-3 py-2 text-xs font-medium uppercase tracking-wide text-text-muted",
                  )}
                >
                  <span>Case</span>
                  <span>Recall@10</span>
                  <span>MRR</span>
                  <span>nDCG@10</span>
                  <span>Pass</span>
                </div>

                {resultsQuery.data.map((result) => (
                  <div
                    key={result.id}
                    className={cn(
                      ROW,
                      "border-b border-border px-3 py-3 text-sm text-text",
                    )}
                  >
                    <span className="font-mono text-xs text-text-muted">
                      {result.case_id}
                    </span>
                    <span className="tabular-nums">
                      {result.scores.recall_at_10?.toFixed(3) ?? "—"}
                    </span>
                    <span className="tabular-nums">
                      {result.scores.mrr?.toFixed(3) ?? "—"}
                    </span>
                    <span className="tabular-nums">
                      {result.scores.ndcg_at_10?.toFixed(3) ?? "—"}
                    </span>
                    <span
                      className={
                        result.passed ? "text-positive" : "text-danger"
                      }
                    >
                      {result.passed ? "✓" : "✗"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
