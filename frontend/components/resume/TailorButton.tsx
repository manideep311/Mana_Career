"use client";

import { useState } from "react";

import Link from "next/link";

import { useMutation, useQuery } from "@tanstack/react-query";

import { BlockView } from "@/components/ai/blocks/block-registry";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import { useTailorRunEvents } from "@/hooks/useTailorRunEvents";
import type { ResumeOut } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** Primary confirmed résumé, else the first confirmed one, else none. */
function pickConfirmed(resumes: ResumeOut[] | undefined): ResumeOut | null {
  if (!resumes) return null;
  const confirmed = resumes.filter((r) => r.confirmed_at != null);
  return confirmed.find((r) => r.is_primary) ?? confirmed[0] ?? null;
}

/**
 * "Tailor résumé for this job" on a Job Detail page. Resolves the user's
 * confirmed résumé itself (mirroring the backend's own primary-or-first-
 * confirmed pick, but sent explicitly — see the Phase 8b spec addendum §1
 * for why the explicit id matters), starts the run, and watches it inline
 * via `useTailorRunEvents` until a `resume_suggestion` block arrives.
 */
export function TailorButton({ jobId }: { jobId: string }) {
  const { api } = useAuth();
  const { toast } = useToast();
  const [run, setRun] = useState<{ sessionId: string; runId: string } | null>(null);

  const resumesQuery = useQuery({ queryKey: qk.resumes, queryFn: () => api.resumes.list() });
  const resume = pickConfirmed(resumesQuery.data);

  const tailorMut = useMutation({
    mutationFn: () => api.resumes.tailor((resume as ResumeOut).id, { job_id: jobId }),
    onSuccess: (ref) => setRun({ sessionId: ref.session_id, runId: ref.run_id }),
    onError: () => toast({ title: "Couldn't start tailoring.", variant: "danger" }),
  });

  const ev = useTailorRunEvents(run?.sessionId ?? null, run?.runId ?? null);

  if (resumesQuery.isPending) {
    return (
      <Button disabled>
        <Spinner size="sm" />
        Tailor résumé for this job
      </Button>
    );
  }

  if (!resume) {
    return (
      <Button disabled title="Confirm a résumé first">
        Tailor résumé for this job
      </Button>
    );
  }

  if (run) {
    if (ev.status === "error") {
      return (
        <Card>
          <CardBody className="flex flex-col items-start gap-2">
            <p className="text-sm text-text">{ev.error}</p>
            <div className="flex items-center gap-3">
              <Button variant="outline" size="sm" onClick={() => setRun(null)}>
                Try again
              </Button>
              <Link
                href="/resume"
                className="text-sm font-medium text-accent underline-offset-4 hover:underline"
              >
                Go to Tailored versions
              </Link>
            </div>
          </CardBody>
        </Card>
      );
    }

    const suggestion = ev.blocks.find((b) => b.kind === "resume_suggestion");
    if (suggestion) {
      return <BlockView block={suggestion} />;
    }

    return (
      <Card>
        <CardBody className="flex items-center gap-2">
          <Spinner size="sm" />
          <p className="text-sm text-text-muted">
            {ev.steps.at(-1)?.summary ?? "Tailoring your résumé for this role…"}
          </p>
        </CardBody>
      </Card>
    );
  }

  return (
    <Button loading={tailorMut.isPending} onClick={() => tailorMut.mutate()}>
      Tailor résumé for this job
    </Button>
  );
}
