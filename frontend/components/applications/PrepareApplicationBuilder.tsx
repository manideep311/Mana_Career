"use client";

import { useState } from "react";

import Link from "next/link";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApprovalCard, type Recipient } from "@/components/applications/ApprovalCard";
import { ErrorState } from "@/components/common/ErrorState";
import { LaunchProgress } from "@/components/motion/LaunchProgress";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import { usePrepareRunEvents } from "@/hooks/usePrepareRunEvents";
import { ProblemError } from "@/lib/api/fetcher";
import type { ApplicationDelivery } from "@/lib/api/types";
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

/** Poll delivery every 2 s for up to ~90 s, then stop and say so (bounded, R11). */
export const DELIVERY_POLL_MS = 2000;
export const DELIVERY_MAX_POLLS = 45;

/** The server's RFC 9457 `detail`, when it sent one. */
function problemDetail(err: unknown): string | null {
  if (err instanceof ProblemError && err.problem && typeof err.problem === "object") {
    const detail = (err.problem as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return null;
}

function sentAt(d: ApplicationDelivery): string {
  return d.sent_at ? ` at ${new Date(d.sent_at).toLocaleTimeString()}` : "";
}

/** Plain words for where the approved email ended up. */
function sentMessage(d: ApplicationDelivery): string {
  if (d.redirected) {
    return `Delivered to your inbox (${d.delivered_to})${sentAt(d)} as a demo. In the live product it goes to ${d.intended_to}.`;
  }
  if (d.delivered_to) {
    return `Application sent to ${d.delivered_to}${sentAt(d)}. A copy is in your inbox.`;
  }
  return `Application recorded as sent${sentAt(d)}. This server doesn't send real email.`;
}

export function PrepareApplicationBuilder({ jobId }: { jobId: string }) {
  const { api, user } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
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

  // Where approved emails go on this server (console / demo redirect / live).
  const metaQuery = useQuery({
    queryKey: qk.meta,
    queryFn: () => api.meta.get(),
    staleTime: Infinity,
    retry: false,
  });

  const decideMut = useMutation({
    mutationFn: (v: { decision: "approve" | "reject"; recipient?: Recipient }) =>
      api.approvals.decide(ev.approvalId as string, { decision: v.decision, ...v.recipient }),
    onSuccess: (_v, v) => setDecided(v.decision),
    onError: (err) =>
      toast({ title: problemDetail(err) ?? "Couldn't record your decision.", variant: "danger" }),
  });

  const deliveryKey = qk.applicationDelivery(applicationId ?? "");
  const deliveryQuery = useQuery({
    queryKey: deliveryKey,
    queryFn: () => api.applications.delivery(applicationId as string),
    enabled: decided === "approve" && applicationId != null,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      if (s === "sent" || s === "failed") return false;
      return q.state.dataUpdateCount >= DELIVERY_MAX_POLLS ? false : DELIVERY_POLL_MS;
    },
  });

  const resendMut = useMutation({
    mutationFn: () => api.applications.send(applicationId as string),
    onSuccess: (d) => queryClient.setQueryData(deliveryKey, d),
    onError: (err) =>
      toast({ title: problemDetail(err) ?? "Couldn't send it again.", variant: "danger" }),
  });

  function startOver() {
    setRun(null);
    setDecided(null);
    setAttempt((a) => a + 1);
  }

  const backLink = (
    <Link href={`/jobs/${jobId}`} className="text-sm font-medium text-accent underline-offset-4 hover:underline">
      Back to the job
    </Link>
  );

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
          {backLink}
        </CardBody>
      </Card>
    );
  }

  const delivery = deliveryQuery.data;

  // --- terminal: sent ---
  if (decided === "approve" && delivery?.status === "sent") {
    return (
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          <p role="status" className="text-sm font-medium text-positive">
            {sentMessage(delivery)}
          </p>
          {backLink}
        </CardBody>
      </Card>
    );
  }

  // --- terminal: the send failed (never retried automatically) ---
  if (decided === "approve" && delivery?.status === "failed") {
    return (
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm font-medium text-danger">
            Your application wasn&apos;t sent.
          </p>
          {delivery.error ? <p className="text-sm text-text-muted">{delivery.error}</p> : null}
          <div className="flex items-center gap-4">
            <Button loading={resendMut.isPending} onClick={() => resendMut.mutate()}>
              Try sending again
            </Button>
            {backLink}
          </div>
        </CardBody>
      </Card>
    );
  }

  // --- sending (approved, polling within a time limit) ---
  if (decided === "approve") {
    const polls = queryClient.getQueryState(deliveryKey)?.dataUpdateCount ?? 0;
    const stalled = deliveryQuery.isError || polls >= DELIVERY_MAX_POLLS;
    return (
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          {stalled ? (
            <>
              <p className="text-sm text-text">
                This is taking longer than usual. Your approval is saved; check your
                applications in a minute.
              </p>
              <Button variant="outline" size="sm" onClick={() => void deliveryQuery.refetch()}>
                Check again
              </Button>
            </>
          ) : (
            <p role="status" className="flex items-center gap-2 text-sm text-text-muted">
              <Spinner size="sm" />
              Sending your application…
            </p>
          )}
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
          onApprove={(recipient) => decideMut.mutate({ decision: "approve", recipient })}
          onReject={() => decideMut.mutate({ decision: "reject" })}
          delivery={metaQuery.data?.email_delivery ?? null}
          applicantEmail={user?.email ?? null}
          emailConfirmed={user?.email_verified ?? true}
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
