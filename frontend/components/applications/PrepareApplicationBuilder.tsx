"use client";

import { useState } from "react";

import Link from "next/link";

import { useMutation, useQuery } from "@tanstack/react-query";

import { ApprovalCard } from "@/components/applications/ApprovalCard";
import { ErrorState } from "@/components/common/ErrorState";
import { LaunchProgress } from "@/components/motion/LaunchProgress";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import { usePrepareRunEvents } from "@/hooks/usePrepareRunEvents";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** The agent's real stages, in order; each node maps onto one of them. */
const STAGES = [
  "Tailoring your résumé to this role…",
  "Checking every claim against your résumé…",
  "Preparing your cover letter…",
  "Drafting your email…",
  "Getting it ready for your review",
] as const;

const NODE_STAGE: Record<string, number> = {
  resume_tailoring: 0,
  claim_validator: 1,
  cover_letter: 2,
  letter_claim_validator: 2,
  email_draft: 3,
  application_prep: 4,
};

export function PrepareApplicationBuilder({ jobId }: { jobId: string }) {
  const { api } = useAuth();
  const { toast } = useToast();
  const [attempt, setAttempt] = useState(0);
  const [run, setRun] = useState<{ sessionId: string; runId: string } | null>(null);
  const [decided, setDecided] = useState<"approve" | "reject" | null>(null);

  const startMut = useMutation({
    mutationFn: () => api.applications.create({ job_id: jobId }),
    onSuccess: (ref) => setRun({ sessionId: ref.session_id, runId: ref.run_id }),
    onError: () => toast({ title: "Couldn't start preparing this application.", variant: "danger" }),
  });

  const ev = usePrepareRunEvents(run?.sessionId ?? null, run?.runId ?? null);

  const approvalQuery = useQuery({
    queryKey: qk.approval(ev.approvalId ?? ""),
    queryFn: () => api.approvals.get(ev.approvalId as string),
    enabled: ev.status === "awaiting_approval" && ev.approvalId != null,
  });
  const applicationId = approvalQuery.data?.application_id ?? null;

  const decideMut = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      api.approvals.decide(ev.approvalId as string, { decision }),
    onSuccess: (_v, decision) => setDecided(decision),
    onError: () => toast({ title: "Couldn't record your decision.", variant: "danger" }),
  });

  const applicationQuery = useQuery({
    queryKey: qk.application(applicationId ?? ""),
    queryFn: () => api.applications.get(applicationId as string),
    enabled: decided === "approve" && applicationId != null,
    refetchInterval: (q) =>
      q.state.data && q.state.data.status !== "awaiting_approval" ? false : 2000,
  });

  function startOver() {
    setRun(null);
    setDecided(null);
    setAttempt((a) => a + 1);
  }

  // --- not started ---
  if (!run) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-text-muted">
          Mana AI will tailor your résumé, write a cover letter, and draft an email —
          then stop and show you everything before anything is sent.
        </p>
        <Button loading={startMut.isPending} onClick={() => startMut.mutate()}>
          Prepare application
        </Button>
      </div>
    );
  }

  // --- terminal: rejected ---
  if (decided === "reject") {
    return (
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          <p className="text-sm text-text">You didn&apos;t approve this application — nothing was sent.</p>
          <Link href={`/jobs/${jobId}`} className="text-sm font-medium text-accent underline-offset-4 hover:underline">
            Back to the job
          </Link>
        </CardBody>
      </Card>
    );
  }

  // --- terminal: sent ---
  if (decided === "approve" && applicationQuery.data?.status === "applied") {
    const at = applicationQuery.data.applied_at;
    return (
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          <p className="text-sm font-medium text-positive">
            Application sent{at ? ` at ${new Date(at).toLocaleTimeString()}` : ""}.
          </p>
          <Link href={`/jobs/${jobId}`} className="text-sm font-medium text-accent underline-offset-4 hover:underline">
            Back to the job
          </Link>
        </CardBody>
      </Card>
    );
  }

  // --- sending (approved, polling) ---
  if (decided === "approve") {
    return (
      <Card>
        <CardBody className="flex items-center gap-2">
          <Spinner size="sm" />
          <p className="text-sm text-text-muted">Sending your application…</p>
        </CardBody>
      </Card>
    );
  }

  // --- error ---
  if (ev.status === "error") {
    return <ErrorState title={ev.error ?? "Something went wrong."} onRetry={startOver} />;
  }

  // --- awaiting approval ---
  if (ev.status === "awaiting_approval") {
    if (approvalQuery.isPending) return <Skeleton className="h-64 w-full" />;
    if (approvalQuery.isError || !approvalQuery.data) {
      return <ErrorState onRetry={() => void approvalQuery.refetch()} />;
    }
    return (
      <div key={attempt}>
        <ApprovalCard
          snapshot={approvalQuery.data.payload_snapshot}
          submitting={decideMut.isPending}
          onApprove={() => decideMut.mutate("approve")}
          onReject={() => decideMut.mutate("reject")}
        />
      </div>
    );
  }

  // --- streaming progress ---
  const last = ev.steps.at(-1);
  const stage = last ? (NODE_STAGE[last.node] ?? 0) : 0;
  return (
    <LaunchProgress
      stages={STAGES}
      current={stage}
      detail={
        last
          ? "Only facts from your résumé are used. Nothing is sent until you approve it."
          : "Preparing your career documents. Nothing is sent until you approve it."
      }
    />
  );
}
