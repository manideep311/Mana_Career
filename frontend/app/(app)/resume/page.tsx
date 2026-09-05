"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useRouter } from "next/navigation";

import {
  skipToken,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { ErrorState } from "@/components/common/ErrorState";
import { ExtractionReview } from "@/components/resume/ExtractionReview";
import { ResumeFailed } from "@/components/resume/ResumeFailed";
import { ResumeList } from "@/components/resume/ResumeList";
import { ResumeStepper } from "@/components/resume/ResumeStepper";
import { ResumeVersionsList } from "@/components/resume/ResumeVersionsList";
import { UploadDropzone } from "@/components/resume/UploadDropzone";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import { ProblemError } from "@/lib/api/fetcher";
import type { ResumeExtraction, ResumeOut, ResumeStatus } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";
import { useResumeEvents } from "@/hooks/useResumeEvents";

/** Pipeline statuses that mean "the résumé is still being worked on". */
const PROCESSING_STATUSES: readonly ResumeStatus[] = [
  "uploaded",
  "parsing",
  "parsed",
  "extracting",
];

/** How long to wait on a silent pipeline before offering a way out. */
const STALL_MS = 3 * 60 * 1000;

type Phase =
  | "loading"
  | "load-error"
  | "idle"
  | "processing"
  | "review"
  | "failed"
  | "list";

/**
 * The terminal outcome the SSE stream reported for the active résumé.
 *
 * `"disconnected"` (the stream died / connection lost) is kept distinct from
 * `"failed"` (the pipeline itself failed): they need different copy, and a
 * disconnect must not trap the user on a "scanned PDF" dead-end.
 */
type StreamOutcome = "extracted" | "failed" | "disconnected" | null;

/** Newest first, by `created_at`. */
function newestFirst(a: ResumeOut, b: ResumeOut): number {
  return (b.created_at ?? "").localeCompare(a.created_at ?? "");
}

/** The RFC 9457 `detail` string of a thrown error, or a generic fallback. */
function errorMessage(err: unknown): string {
  if (
    err instanceof ProblemError &&
    err.problem !== null &&
    typeof err.problem === "object" &&
    "detail" in err.problem &&
    typeof (err.problem as { detail: unknown }).detail === "string"
  ) {
    return (err.problem as { detail: string }).detail;
  }
  return "Something went wrong.";
}

/**
 * `/resume` — the résumé flow state machine.
 *
 * `upload → activeId → useResumeEvents(activeId) drives the stepper → on
 * extracted, GET the extraction → edit → confirm → invalidate ["profile"] →
 * /dashboard`. A returning user whose résumés are all confirmed/failed sees the
 * `<ResumeList>` plus a dropzone instead of the flow.
 *
 * `phase` is derived, every render, from the résumé list, `activeId`, the
 * sticky `streamOutcome`, `reuploadRequested`, and the upload mutation's pending
 * flag — never a `useReducer`. `useResumeEvents` is only enabled while
 * `phase === "processing"`.
 */
export default function ResumePage() {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const router = useRouter();
  const { toast } = useToast();

  const [activeId, setActiveId] = useState<string | null>(null);
  const [streamOutcome, setStreamOutcome] = useState<StreamOutcome>(null);
  // Set by "Upload a different file": suppresses implicit-active adoption so the
  // user actually lands on (and stays on) the dropzone instead of being bounced
  // straight back onto the résumé whose stream just dropped (its DB row is still
  // `extracting`, so it would otherwise be re-adopted immediately).
  const [reuploadRequested, setReuploadRequested] = useState(false);
  // Wall-clock escape hatch: a worker that dies mid-extraction never sends
  // `done`, so `phase` would sit on "processing" forever.
  const [stalled, setStalled] = useState(false);
  const uploadAnotherRef = useRef<HTMLDivElement>(null);

  const resumesQuery = useQuery({
    queryKey: qk.resumes,
    queryFn: () => api.resumes.list(),
  });
  const resumes = resumesQuery.data;

  function requestReupload() {
    setActiveId(null);
    setReuploadRequested(true);
  }

  /**
   * The résumé the flow is currently about: the explicitly selected / just-
   * uploaded one, or — when nothing is selected and no reupload is pending —
   * the newest résumé that is neither confirmed nor failed (the implicit active
   * one).
   */
  const activeResume: ResumeOut | null = useMemo(() => {
    if (!resumes) return null;
    if (activeId !== null) {
      return resumes.find((r) => r.id === activeId) ?? null;
    }
    if (reuploadRequested) return null;
    return (
      [...resumes]
        .filter((r) => !r.confirmed_at && r.status !== "failed")
        .sort(newestFirst)[0] ?? null
    );
  }, [resumes, activeId, reuploadRequested]);

  // Adopt the implicit active résumé into `activeId` so the mutations that key
  // off it (confirm, retry) and the extraction query have a concrete id — but
  // never while the user has asked to upload a different file.
  useEffect(() => {
    if (reuploadRequested) return;
    if (activeId === null && activeResume) {
      setActiveId(activeResume.id);
    }
  }, [activeId, activeResume, reuploadRequested]);

  // A new active résumé starts with a clean slate — drop any stale stream verdict.
  useEffect(() => {
    setStreamOutcome(null);
  }, [activeId]);

  const phase: Phase = useMemo(() => {
    if (resumesQuery.isPending) return "loading";
    if (resumesQuery.isError) return "load-error";

    const confirmed = activeResume?.confirmed_at != null;
    const streamFailed =
      streamOutcome === "failed" || streamOutcome === "disconnected";

    if (activeResume) {
      if (activeResume.status === "failed" || streamFailed) {
        return "failed";
      }
      if (
        !confirmed &&
        (activeResume.status === "extracted" || streamOutcome === "extracted")
      ) {
        return "review";
      }
      if (PROCESSING_STATUSES.includes(activeResume.status)) return "processing";
      // A confirmed / otherwise-settled active résumé — no live flow.
      return resumes && resumes.length > 0 ? "list" : "idle";
    }

    // `activeId` set but the list has not caught up yet: lean on the stream.
    if (activeId !== null) {
      if (streamFailed) return "failed";
      if (streamOutcome === "extracted") return "review";
      return "processing";
    }

    return resumes && resumes.length > 0 ? "list" : "idle";
  }, [
    resumesQuery.isPending,
    resumesQuery.isError,
    activeResume,
    activeId,
    resumes,
    streamOutcome,
  ]);

  const ev = useResumeEvents(activeId, { enabled: phase === "processing" });

  // When the stream signals completion, remember its verdict (so `phase` stays
  // put once it leaves "processing" and the hook resets) and re-read the list so
  // the server's own `status` / `parse_error` catch up. Guarded on `ev.done`.
  //   - `ev.error` present  → "disconnected" (transport died; file may be fine)
  //   - status "failed"     → "failed"       (the pipeline itself failed)
  //   - status "extracted"  → "extracted"
  useEffect(() => {
    if (!ev.done) return;
    if (ev.error !== null) {
      setStreamOutcome("disconnected");
    } else if (ev.status === "failed") {
      setStreamOutcome("failed");
    } else if (ev.status === "extracted") {
      setStreamOutcome("extracted");
    }
    void queryClient.invalidateQueries({ queryKey: qk.resumes });
  }, [ev.done, ev.error, ev.status, queryClient]);

  // Wall-clock ceiling on "processing": arm a timer whenever we enter it, clear
  // it on any phase change or once the stream is done.
  useEffect(() => {
    if (phase !== "processing" || ev.done) {
      setStalled(false);
      return;
    }
    const t = setTimeout(() => setStalled(true), STALL_MS);
    return () => clearTimeout(t);
  }, [phase, ev.done]);

  const reviewId = phase === "review" ? (activeResume?.id ?? activeId) : null;
  const extractionQuery = useQuery({
    queryKey: qk.resumeExtraction(reviewId),
    queryFn: reviewId ? () => api.resumes.extraction(reviewId) : skipToken,
  });

  function onMutationError(err: unknown) {
    toast({ title: errorMessage(err), variant: "danger" });
  }

  const uploadMut = useMutation({
    mutationFn: (file: File) => api.resumes.upload(file),
    onSuccess: (r) => {
      setReuploadRequested(false);
      setActiveId(r.id);
      void queryClient.invalidateQueries({ queryKey: qk.resumes });
    },
    onError: onMutationError,
  });

  const confirmMut = useMutation({
    mutationFn: (e: ResumeExtraction) =>
      api.resumes.confirmProfile(activeId as string, e),
    onSuccess: async () => {
      void queryClient.invalidateQueries({ queryKey: qk.profile });
      // Await the résumés refetch so the dashboard's "finish setting up your
      // profile" nudge doesn't flash on arrival before the list shows the
      // now-confirmed résumé.
      await queryClient.invalidateQueries({ queryKey: qk.resumes });
      toast({ title: "Profile updated from your résumé" });
      router.push("/dashboard");
    },
    onError: onMutationError,
  });

  const retryMut = useMutation({
    mutationFn: (id: string) => api.resumes.reprocess(id),
    onSuccess: () => {
      setStreamOutcome(null);
      return queryClient.invalidateQueries({ queryKey: qk.resumes });
    },
    onError: onMutationError,
  });

  const setPrimaryMut = useMutation({
    mutationFn: (id: string) => api.resumes.patch(id, { is_primary: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.resumes }),
    onError: onMutationError,
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.resumes.remove(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: qk.resumes });
      if (id === activeId) setActiveId(null);
    },
    onError: onMutationError,
  });

  const busyId = setPrimaryMut.isPending
    ? (setPrimaryMut.variables ?? null)
    : retryMut.isPending
      ? (retryMut.variables ?? null)
      : deleteMut.isPending
        ? (deleteMut.variables ?? null)
        : null;

  function uploadArea() {
    return (
      <div className="flex flex-col gap-2">
        <UploadDropzone
          onFile={(f) => uploadMut.mutate(f)}
          disabled={uploadMut.isPending}
        />
        {uploadMut.isPending ? (
          <p className="flex items-center gap-2 text-sm text-text-muted">
            <Spinner size="sm" />
            Uploading…
          </p>
        ) : null}
      </div>
    );
  }

  function body() {
    if (phase === "loading") {
      return (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      );
    }

    if (phase === "load-error") {
      return <ErrorState onRetry={() => void resumesQuery.refetch()} />;
    }

    if (phase === "processing") {
      return (
        <div className="flex flex-col gap-4">
          {stalled ? (
            <Card>
              <CardBody className="flex flex-col items-start gap-3">
                <p className="text-sm text-text">
                  This is taking longer than usual.
                </p>
                <Button variant="outline" onClick={requestReupload}>
                  Upload a different file
                </Button>
              </CardBody>
            </Card>
          ) : null}
          <ResumeStepper
            status={ev.status ?? activeResume?.status ?? null}
            message={ev.message}
          />
        </div>
      );
    }

    if (phase === "review") {
      if (extractionQuery.isPending) {
        return (
          <div className="flex flex-col gap-4">
            <Skeleton className="h-8 w-40" />
            <Skeleton className="h-64 w-full" />
          </div>
        );
      }
      if (extractionQuery.isError || !extractionQuery.data) {
        return <ErrorState onRetry={() => void extractionQuery.refetch()} />;
      }
      return (
        <ExtractionReview
          extraction={extractionQuery.data}
          onConfirm={(e) => confirmMut.mutateAsync(e)}
          confirming={confirmMut.isPending}
        />
      );
    }

    if (phase === "failed") {
      const target = activeResume?.id ?? activeId;
      const isConnection = streamOutcome === "disconnected";
      const message = isConnection
        ? ev.error
        : (activeResume?.parse_error ?? null);
      if (target) {
        return (
          <ResumeFailed
            kind={isConnection ? "connection" : "pipeline"}
            message={message}
            onRetry={() => retryMut.mutate(target)}
            onReupload={requestReupload}
            retrying={retryMut.isPending}
          />
        );
      }
    }

    if (phase === "list" && resumes) {
      return (
        <div className="flex flex-col gap-8">
          <ResumeList
            resumes={resumes}
            onSetPrimary={(id) => setPrimaryMut.mutate(id)}
            onReview={(id) => setActiveId(id)}
            onRetry={(id) => retryMut.mutate(id)}
            onDelete={(id) => deleteMut.mutate(id)}
            onUploadAnother={() => {
              setActiveId(null);
              uploadAnotherRef.current?.scrollIntoView({ block: "center" });
            }}
            busyId={busyId}
          />
          {(() => {
            const confirmed = resumes.filter((r) => r.confirmed_at != null);
            const target = confirmed.find((r) => r.is_primary) ?? confirmed[0];
            return target ? <ResumeVersionsList resumeId={target.id} /> : null;
          })()}
          <div ref={uploadAnotherRef} className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-text">
              Upload another résumé
            </h2>
            {uploadArea()}
          </div>
        </div>
      );
    }

    // phase === "idle"
    return uploadArea();
  }

  return (
    <RequireAuth>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-text">Your résumé</h1>
          <p className="text-sm text-text-muted">
            Upload a PDF and we&apos;ll turn it into your career profile.
          </p>
        </header>
        {body()}
      </div>
    </RequireAuth>
  );
}
